from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional

from clinic_mcp_server.domain.enums import MembershipType
from clinic_mcp_server.domain.errors import ValidationError
from clinic_mcp_server.domain.interfaces import ClinicRepository
from clinic_mcp_server.model.clinic_db import AppointmentSlot, DoctorSearchResult, PaymentMethod, User


def _validate_date(d: Optional[str], name: str) -> Optional[str]:
    if d is None:
        return None
    if len(d) != 10 or d[4] != "-" or d[7] != "-":
        raise ValidationError(f"{name} must be YYYY-MM-DD. Got: {d!r}")
    return d





@dataclass(frozen=True)
class RegisterUserResult:
    user_id: int
    pay_id: int
    bill_id: int


class ClinicService:
    def __init__(self, repo: ClinicRepository):
        self.repo = repo
        

    # ----- Workflows -----
    def register_user(
        self,
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
        membership_type: MembershipType
,
    ) -> RegisterUserResult:
       

        user_id = self.repo.add_user(
            social_security_number,
            first_name,
            last_name,
            address,
            email,
            phone_number,
            membership_type,
        )
        pay_id = self.repo.add_payment_method(user_id, card_last_4, card_brand, card_exp, card_id)
        bill_id = self.repo.bill_user(pay_id, float(amount))
        return RegisterUserResult(user_id=user_id, pay_id=pay_id, bill_id=bill_id)

    def add_payment_method(self, user_id: int, card_last_4: int, card_brand: str, card_exp: str, card_id: str) -> int:
        return self.repo.add_payment_method(user_id, card_last_4, card_brand, card_exp, card_id)

    def get_user_payment_methods(self, user_id: int) -> List[PaymentMethod]:
        return self.repo.get_user_payment_methods(user_id)

    def list_specialties(self) -> List[str]:
        return self.repo.get_available_dr_specialties()

    def search_doctors(
        self, specialty: Optional[str] = None, min_rank: Optional[float] = None, max_fee: Optional[float] = None
    ) -> List[DoctorSearchResult]:
        return self.repo.search_doctors(specialty, min_rank, max_fee)

    def search_appointments(
        self, specialty: str, doctor_name: Optional[str] = None, start_date: Optional[str] = None, end_date: Optional[str] = None
    ) -> List[AppointmentSlot]:
        start_date = _validate_date(start_date, "start_date")
        end_date = _validate_date(end_date, "end_date")
        return self.repo.search_available_appointments(specialty, doctor_name, start_date, end_date)

    def get_slot(self, slot_id: int) -> Optional[AppointmentSlot]:
        return self.repo.get_appointment_slot(slot_id)

    def schedule_appointment(self, user_id: int, pay_id: int, slot_id: int, payment_amount: float) -> int:
        booked = self.repo.add_appointment(user_id, slot_id)
        self.repo.bill_user(pay_id, float(payment_amount), slot_id=booked)
        return booked

    def cancel_appointment(self, slot_id: int) -> None:
        self.repo.remove_appointment(slot_id)

    def get_user_appointments(self, user_id: int) -> List[AppointmentSlot]:
        return self.repo.get_user_appointments(user_id)

    def get_user_id(self, ssn: int) -> int:
        return self.repo.get_user_id(ssn)

    def get_user(self, user_id: int) -> User:
        return self.repo.get_user(user_id)
