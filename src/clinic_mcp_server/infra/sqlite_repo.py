from __future__ import annotations
import os
from pathlib import Path
from typing import List, Literal, Optional

from clinic_mcp_server.domain.enums import MembershipType
from clinic_mcp_server.domain.errors import ConflictError, NotFoundError, ValidationError
from clinic_mcp_server.domain.interfaces import ClinicRepository
from clinic_mcp_server.model.clinic_db import (
    AppointmentSlot,
    ClinicDB,
    DoctorSearchResult,
    PaymentMethod,
    User,
)


class SQLiteClinicRepository(ClinicRepository):
    def __init__(self, db_path: str):
        self._db_path = db_path

    def init_schema(self) -> None:
        with ClinicDB(self._db_path) as db:
            db.init_schema(seed=True)

    def _db(self) -> ClinicDB:
        return ClinicDB(self._db_path)
    

    def hard_reset_database(self) -> None:
        """
        Delete SQLite DB file and recreate schema (+ optional seed).
        Deterministic and safest for demos/tests.
        """
        db_path = Path(self._db_path)
        if db_path.parent and str(db_path.parent) != ".":
            db_path.parent.mkdir(parents=True, exist_ok=True)

        if db_path.exists():
            # ensure no open connection is holding the file
            # (ClinicDB context manager closes connections per call)
            os.remove(db_path)

        # bootstrap
        self.init_schema()


    def reset_database(self, *, seed: bool = True) -> None:
        with ClinicDB(self._db_path) as db:
            db.reset_schema(seed=seed)    



    # ---- Users ----
    def add_user(
        self,
        social_security_number: int,
        first_name: str,
        last_name: str,
        address: str,
        email: str,
        phone_number: str,
        membership_type: MembershipType
    ) -> int:
        try:
            with self._db() as db:
                return db.add_user(
                    social_security_number,
                    first_name,
                    last_name,
                    address,
                    email,
                    phone_number,
                    membership_type,
                )
        except ValueError as e:
            raise ValidationError(str(e)) from e

    def get_user_id(self, social_security_number: int) -> int:
        try:
            with self._db() as db:
                return db.get_user_id(social_security_number)
        except ValueError as e:
            raise NotFoundError(str(e)) from e

    def get_user(self, user_id: int) -> User:
        try:
            with self._db() as db:
                return db.get_user(user_id)
        except ValueError as e:
            raise NotFoundError(str(e)) from e

    # ---- Payments ----
    def add_payment_method(
        self, user_id: int, card_last_4: int, card_brand: str, card_exp: str, card_id: str
    ) -> int:
        with self._db() as db:
            return db.add_payment_method(user_id, card_last_4, card_brand, card_exp, card_id)

    def get_user_payment_methods(self, user_id: int) -> List[PaymentMethod]:
        with self._db() as db:
            return db.get_user_payment_methods(user_id)

    def bill_user(self, pay_id: int, amount: float, slot_id: Optional[int] = None) -> int:
        with self._db() as db:
            return db.bill_user(pay_id, amount, slot_id)

    # ---- Doctors & slots ----
    def get_available_dr_specialties(self) -> List[str]:
        with self._db() as db:
            return db.get_available_dr_specialties()

    def search_doctors(
        self, specialty: Optional[str] = None, min_rank: Optional[float] = None, max_fee: Optional[float] = None
    ) -> List[DoctorSearchResult]:
        with self._db() as db:
            return db.search_doctors(specialty, min_rank, max_fee)

    def search_available_appointments(
        self,
        specialty: str,
        doctor_name: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[AppointmentSlot]:
        with self._db() as db:
            return db.search_available_appointments(specialty, doctor_name, start_date, end_date)

    def get_appointment_slot(self, slot_id: int) -> Optional[AppointmentSlot]:
        with self._db() as db:
            return db.get_appointment_slot(slot_id)

    def add_appointment(self, user_id: int, slot_id: int) -> int:
        try:
            with self._db() as db:
                return db.add_appointment(user_id, slot_id)
        except ValueError as e:
            # your DB raises ValueError when slot not available
            raise ConflictError(str(e)) from e

    def remove_appointment(self, slot_id: int) -> None:
        with self._db() as db:
            db.remove_appointment(slot_id)

    def get_user_appointments(self, user_id: int) -> List[AppointmentSlot]:
        with self._db() as db:
            return db.get_user_appointments(user_id)
