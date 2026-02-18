from __future__ import annotations

import os
from functools import lru_cache

from fastmcp import FastMCP

from clinic_mcp_server.domain.default_values import DEFAULT_DB_PATH
from clinic_mcp_server.domain.enums import MembershipType
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

# ---- Tool functions (thin wrappers) ----
@mcp.tool()
def add_user(
    social_security_number: int,
    first_name: str,
    last_name: str,
    address: str,
    email: str,
    phone_number: str,
    card_last_4: int,
    card_brand: str,
    card_exp: str,
    card_id: str,
    amount: float,
    membership_type: str = "regular",
) -> int:
    svc = get_service()
    try:
        membership = MembershipType(membership_type)
        result = svc.register_user(
            social_security_number, first_name, last_name, address, email, phone_number,
            card_last_4, card_brand, card_exp, card_id, amount, membership,
        )
        return result.user_id
    except ValueError as ve:
        raise ValueError(
            f"Invalid membership_type '{membership_type}'. "
            f"Allowed: {[m.value for m in MembershipType]}"
        ) from ve
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e

@mcp.tool()
def add_payment_method(user_id: int, card_last_4: int, card_brand: str, card_exp: str, card_id: str) -> int:
    svc = get_service()
    try:
        return svc.add_payment_method(user_id, card_last_4, card_brand, card_exp, card_id)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_user_payment_methods(user_id: int) -> list[PaymentMethod]:
    svc = get_service()
    try:
        return svc.get_user_payment_methods(user_id)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_available_dr_specialties() -> list[str]:
    svc = get_service()
    try:
        return svc.list_specialties()
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def search_doctors(
    specialty: str | None = None, min_rank: float | None = None, max_fee: float | None = None
) -> list[DoctorSearchResult]:
    svc = get_service()
    try:
        return svc.search_doctors(specialty, min_rank, max_fee)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def search_available_appointments(
    specialty: str, doctor_name: str | None = None, start_date: str | None = None, end_date: str | None = None
) -> list[AppointmentSlot]:
    svc = get_service()
    try:
        return svc.search_appointments(specialty, doctor_name, start_date, end_date)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_appointment_slot(slot_id: int) -> AppointmentSlot | None:
    svc = get_service()
    try:
        return svc.get_slot(slot_id)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def schedule_appointment(user_id: int, pay_id: int, slot_id: int, payment_amount: float) -> int:
    svc = get_service()
    try:
        return svc.schedule_appointment(user_id, pay_id, slot_id, payment_amount)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def remove_appointment(slot_id: int) -> None:
    svc = get_service()
    try:
        svc.cancel_appointment(slot_id)
        return None
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_user_appointments(user_id: int) -> list[AppointmentSlot]:
    svc = get_service()
    try:
        return svc.get_user_appointments(user_id)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_user_id(social_security_number: int) -> int:
    svc = get_service()
    try:
        return svc.get_user_id(social_security_number)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def get_user(user_id: int) -> User:
    svc = get_service()
    try:
        return svc.get_user(user_id)
    except ClinicError as e:
       raise ValueError(f"{e.code}: {e}") from e


@mcp.tool()
def admin_reset_db() -> str:
    repo = SQLiteClinicRepository(db_path=os.getenv("CLINIC_DB_PATH", DEFAULT_DB_PATH))
    repo.reset_database()
    return "ok"


if __name__ == "__main__":
    mcp.run()
