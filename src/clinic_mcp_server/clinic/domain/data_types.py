from pydantic import BaseModel, Field
from .strenum import StrEnum

class MembershipType(StrEnum):
    REGULAR = "regular"
    SILVER = "silver"
    GOLD = "gold"


class CardBrand(StrEnum):
    visa = "visa"
    mastercard = "mastercard"
    amex = "amex"
    discover = "discover"
    diners = "diners"
    jcb = "jcb"
    unionpay = "unionpay"
    other = "other"


class User(BaseModel):
    user_id: str
    ssn: int
    first_name: str
    last_name: str
    address: str
    email: str
    phone: str
    enter_date: str
    membership_type: MembershipType


class PaymentMethod(BaseModel):
    pay_id: int = Field(..., description="Internal ID of the payment method.")
    card_last_4: int = Field(..., description="Last 4 digits of the card number.")
    card_brand: str = Field(..., description='Brand of the card (e.g., "Visa", "MasterCard").')
    card_exp: str = Field(..., description="Expiration date in MM/YY format.")
    card_id: str = Field(..., description="Unique identifier used to store the card securely.")


class DoctorSearchResult(BaseModel):
    dr_id: int = Field(..., description="Doctor's unique ID.")
    dr_name: str = Field(..., description="Doctor's full name.")
    specialty: str = Field(..., description="Medical specialty.")
    rating: float = Field(..., description="Average patient rating.")
    visit_fee: float = Field(..., description="Consultation fee.")
    next_available_appointment: str | None = Field(
        None, description="Next available appointment date and time, or None if unavailable."
    )


class AppointmentSlot(BaseModel):
    slot_id: int = Field(..., description="Unique identifier of the slot.")
    dr_name: str = Field(..., description="Doctor's name.")
    specialty: str = Field(..., description="Doctor's specialty.")
    date: str = Field(..., description="Date of the appointment (YYYY-MM-DD).")
    start_time: str = Field(..., description="Start time of the appointment (HH:MM format).")
    end_time: str = Field(..., description="End time of the appointment (HH:MM format).")
    visit_fee: float = Field(..., description="Cost of the visit.")
    rating: float = Field(..., description="Doctor's average rating.")

class ClinicError(Exception):
    code: str = "clinic_error"
    def __init__(self, message: str):
        super().__init__(message)

class NotFoundError(ClinicError):
    code = "not_found"


class ValidationError(ClinicError):
    code = "validation_error"


class ConflictError(ClinicError):
    code = "conflict"
