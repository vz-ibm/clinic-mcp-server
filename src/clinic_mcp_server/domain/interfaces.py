from __future__ import annotations
from typing import List, Literal, Optional, Protocol

from clinic_mcp_server.domain.enums import MembershipType
from clinic_mcp_server.model.clinic_db import (
    AppointmentSlot,
    DoctorSearchResult,
    PaymentMethod,
    User,
)


class ClinicRepository(Protocol):
    # Users
    def add_user(
        self,
        social_security_number: int,
        first_name: str,
        last_name: str,
        address: str,
        email: str,
        phone_number: str,
        membership_type: MembershipType,
    ) -> int: ...

    def get_user_id(self, social_security_number: int) -> int: ...
    def get_user(self, user_id: int) -> User: ...

    # Payments
    def add_payment_method(
        self, user_id: int, card_last_4: int, card_brand: str, card_exp: str, card_id: str
    ) -> int: ...

    def get_user_payment_methods(self, user_id: int) -> List[PaymentMethod]: ...

    def bill_user(self, pay_id: int, amount: float, slot_id: Optional[int] = None) -> int: ...

    # Doctors & slots
    def get_available_dr_specialties(self) -> List[str]: ...
    def search_doctors(
        self, specialty: Optional[str] = None, min_rank: Optional[float] = None, max_fee: Optional[float] = None
    ) -> List[DoctorSearchResult]: ...

    def search_available_appointments(
        self,
        specialty: str,
        doctor_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[AppointmentSlot]: ...

    def get_appointment_slot(self, slot_id: int) -> Optional[AppointmentSlot]: ...
    def add_appointment(self, user_id: int, slot_id: int) -> int: ...
    def remove_appointment(self, slot_id: int) -> None: ...
    def get_user_appointments(self, user_id: int) -> List[AppointmentSlot]: ...
