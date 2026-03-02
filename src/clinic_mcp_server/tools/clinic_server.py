from __future__ import annotations
import os
from functools import lru_cache
from typing import Annotated, Optional

from fastmcp import FastMCP
from pydantic import BaseModel, Field

from clinic_mcp_server.domain.default_values import DEFAULT_DB_PATH
from clinic_mcp_server.domain.enums import CardBrand, MembershipType
from clinic_mcp_server.domain.errors import (
    ClinicError,
)
from clinic_mcp_server.infra.sqlite_repo import SQLiteClinicRepository
from clinic_mcp_server.model.clinic_db import (
    AppointmentSlot,
    DoctorSearchResult,
    PaymentMethod,
    User,
)
from clinic_mcp_server.services.clinic_service import ClinicService


@lru_cache(maxsize=1)
def get_service() -> ClinicService:
    db_path = os.getenv("CLINIC_DB_PATH", DEFAULT_DB_PATH)
    repo = SQLiteClinicRepository(db_path=db_path)
    repo.init_schema()  # do once
    return ClinicService(repo)


mcp = FastMCP()


class AddUserResult(BaseModel):
    """Result of creating a user."""
    user_id: int = Field(description="Created user id")


class AddPaymentMethodResult(BaseModel):
    """Result of adding a payment method."""
    payment_method_id: int = Field(description="Created payment method id")


class ScheduleAppointmentResult(BaseModel):
    """Result of scheduling an appointment."""
    appointment_id: int = Field(description="Scheduled appointment id")


class OkResult(BaseModel):
    """Generic success result."""
    ok: bool = Field(description="True if operation succeeded")


@mcp.tool()
def add_user(
    social_security_number: Annotated[
        int,
        Field(description="User national identifier / SSN (digits only)."),
    ],
    first_name: Annotated[
        str,
        Field(description="User first name (given name).", min_length=1),
    ],
    last_name: Annotated[
        str,
        Field(description="User last name (family name).", min_length=1),
    ],
    address: Annotated[
        str,
        Field(description="Full postal address.", min_length=3),
    ],
    email: Annotated[
        str,
        Field(description="User email address.", examples=["john.doe@example.com"]),
    ],
    phone_number: Annotated[
        str,
        Field(description="User phone number (preferably including country code).", examples=["+972501234567"]),
    ],
    card_last_4: Annotated[
        int,
        Field(description="Last 4 digits of the payment card.", ge=0, le=9999),
    ],
    card_brand: Annotated[
        CardBrand,
        Field(description="Payment card brand."),
    ],
    card_exp: Annotated[
        str,
        Field(description="Card expiry in MM/YY format.", examples=["12/28"]),
    ],
    card_id: Annotated[
        str,
        Field(description="Payment provider card token/id (not raw card number)."),
    ],
    amount: Annotated[
        float,
        Field(description="Initial payment amount to charge.", gt=0),
    ],
    membership_type: Annotated[
        MembershipType,
        Field(description="Membership tier for the user.")
    ] = MembershipType.REGULAR,
) -> AddUserResult:
    """
    Register a new user and attach an initial payment method.

    Creates a user record and registers membership details.
    Returns the created user's id.

    Errors:
      - ValueError: for invalid membership type or domain errors mapped from ClinicError.
    """
    svc = get_service()
    try:
        result = svc.register_user(
            social_security_number,
            first_name,
            last_name,
            address,
            email,
            phone_number,
            card_last_4,
            card_brand.value,
            card_exp,
            card_id,
            amount,
            membership_type,
        )
        return AddUserResult(user_id=result.user_id)
    except ValueError as ve:
        raise ValueError(
            f"Invalid membership_type '{membership_type}'. "
            f"Allowed: {[m.value for m in MembershipType]}"
        ) from ve
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def add_payment_method(
    user_id: Annotated[int, Field(description="Existing user id.", gt=0)],
    card_last_4: Annotated[int, Field(description="Last 4 digits of the card.", ge=0, le=9999)],
    card_brand: Annotated[CardBrand, Field(description="Payment card brand.")],
    card_exp: Annotated[str, Field(description="Card expiry in MM/YY format.", examples=["12/28"])],
    card_id: Annotated[str, Field(description="Payment provider card token/id (not raw card number).")],
) -> AddPaymentMethodResult:
    """
    Add a payment method to an existing user.

    Returns the created payment method id.
    """
    svc = get_service()
    try:
        pm_id = svc.add_payment_method(user_id, card_last_4, card_brand.value, card_exp, card_id)
        return AddPaymentMethodResult(payment_method_id=pm_id)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_user_payment_methods(
    user_id: Annotated[int, Field(description="User id to retrieve payment methods for.", gt=0)]
) -> list[PaymentMethod]:
    """
    List all saved payment methods for a user.

    Returns a list of PaymentMethod objects.
    """
    svc = get_service()
    try:
        return svc.get_user_payment_methods(user_id)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_available_dr_specialties() -> list[str]:
    """
    Get a list of all supported doctor specialties.
    """
    svc = get_service()
    try:
        return svc.list_specialties()
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def search_doctors(
    specialty: Annotated[Optional[str], Field(description="Filter by specialty (exact match).")] = None,
    min_rank: Annotated[Optional[float], Field(description="Minimum doctor rank (inclusive).", ge=0, le=5)] = None,
    max_fee: Annotated[Optional[float], Field(description="Maximum visit fee (inclusive).", ge=0)] = None,
) -> list[DoctorSearchResult]:
    """
    Search doctors by optional criteria.

    You can filter by specialty, rank range and/or fee upper bound.
    """
    svc = get_service()
    try:
        return svc.search_doctors(specialty, min_rank, max_fee)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def search_available_appointments(
    specialty: Annotated[str, Field(description="Required specialty to search appointments for.")],
    doctor_name: Annotated[Optional[str], Field(description="Optional doctor name filter (substring match).")] = None,
    start_date: Annotated[
        Optional[str],
        Field(description="Start date (YYYY-MM-DD). If omitted, starts from today.", examples=["2026-03-01"]),
    ] = None,
    end_date: Annotated[
        Optional[str],
        Field(description="End date (YYYY-MM-DD). If omitted, open-ended.", examples=["2026-03-31"]),
    ] = None,
) -> list[AppointmentSlot]:
    """
    Search available appointment slots.

    Dates are expected in YYYY-MM-DD format.
    """
    svc = get_service()
    try:
        return svc.search_appointments(specialty, doctor_name, start_date, end_date)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_appointment_slot(
    slot_id: Annotated[int, Field(description="Appointment slot id.", gt=0)]
) -> Optional[AppointmentSlot]:
    """
    Get a single appointment slot by id.

    Returns the slot or null if not found.
    """
    svc = get_service()
    try:
        return svc.get_slot(slot_id)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def schedule_appointment(
    user_id: Annotated[int, Field(description="User id scheduling the appointment.", gt=0)],
    pay_id: Annotated[int, Field(description="Payment method id to charge.", gt=0)],
    slot_id: Annotated[int, Field(description="Appointment slot id to book.", gt=0)],
    payment_amount: Annotated[float, Field(description="Amount to charge for the appointment.", gt=0)],
) -> ScheduleAppointmentResult:
    """
    Book an appointment slot for a user and charge the selected payment method.

    Returns the created appointment id.
    """
    svc = get_service()
    try:
        appt_id = svc.schedule_appointment(user_id, pay_id, slot_id, payment_amount)
        return ScheduleAppointmentResult(appointment_id=appt_id)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def remove_appointment(
    slot_id: Annotated[int, Field(description="Appointment slot id to cancel.", gt=0)]
) -> OkResult:
    """
    Cancel an appointment by slot id.
    """
    svc = get_service()
    try:
        svc.cancel_appointment(slot_id)
        return OkResult(ok=True)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_user_appointments(
    user_id: Annotated[int, Field(description="User id to list appointments for.", gt=0)]
) -> list[AppointmentSlot]:
    """
    List appointments for a user.
    """
    svc = get_service()
    try:
        return svc.get_user_appointments(user_id)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_user_id(
    social_security_number: Annotated[int, Field(description="User national identifier / SSN (digits only).")]
) -> int:
    """
    Resolve internal user id by social security number.
    """
    svc = get_service()
    try:
        return svc.get_user_id(social_security_number)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_user(
    user_id: Annotated[int, Field(description="User id to retrieve.", gt=0)]
) -> User:
    """
    Retrieve a user record by id.
    """
    svc = get_service()
    try:
        return svc.get_user(user_id)
    except ClinicError as e:
        raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def admin_reset_db() -> OkResult:
    """
    ADMIN: Reset the clinic database.

    Warning: This deletes all data.
    """
    repo = SQLiteClinicRepository(db_path=os.getenv("CLINIC_DB_PATH", DEFAULT_DB_PATH))
    repo.reset_database()
    return OkResult(ok=True)

if __name__ == "__main__":
    mcp.run()
