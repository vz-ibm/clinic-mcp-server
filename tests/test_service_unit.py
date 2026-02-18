import pytest
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from clinic_mcp_server.domain.enums import MembershipType
from clinic_mcp_server.domain.errors import ConflictError, NotFoundError, ValidationError
from clinic_mcp_server.domain.interfaces import ClinicRepository
from clinic_mcp_server.model.clinic_db import AppointmentSlot, DoctorSearchResult, PaymentMethod, User
from clinic_mcp_server.services.clinic_service import ClinicService


@dataclass
class BillCall:
    pay_id: int
    amount: float
    slot_id: Optional[int]


class FakeRepo(ClinicRepository):
    """
    Fake in-memory repo with observability:
    - captures bill calls
    - supports basic filtering for doctors/appointments
    - enforces double-book prevention
    """

    def __init__(self):
        self.users: Dict[int, User] = {}
        self.user_by_ssn: Dict[int, int] = {}
        self.payment: Dict[int, List[PaymentMethod]] = {}
        self._uid = 0
        self._pid = 0
        self._bill_id = 0

        self.bill_calls: List[BillCall] = []

        # doctors (minimal)
        self.doctors: List[DoctorSearchResult] = [
            DoctorSearchResult(dr_id=1, dr_name="Dr Alice", specialty="family", rating=4.7, visit_fee=100.0, next_available_appointment=None),
            DoctorSearchResult(dr_id=2, dr_name="Dr Bob", specialty="family", rating=4.2, visit_fee=150.0, next_available_appointment=None),
            DoctorSearchResult(dr_id=3, dr_name="Dr Carol", specialty="dermatology", rating=4.9, visit_fee=200.0, next_available_appointment=None),
        ]

        # slots
        self.slots: Dict[int, AppointmentSlot] = {
            1: AppointmentSlot(slot_id=1, dr_name="Dr Alice", specialty="family", date="2030-01-01", start_time="09:00", end_time="09:30", visit_fee=100.0, rating=4.7),
            2: AppointmentSlot(slot_id=2, dr_name="Dr Bob", specialty="family", date="2030-01-02", start_time="10:00", end_time="10:30", visit_fee=150.0, rating=4.2),
            3: AppointmentSlot(slot_id=3, dr_name="Dr Carol", specialty="dermatology", date="2030-01-03", start_time="11:00", end_time="11:30", visit_fee=200.0, rating=4.9),
        }
        self.slot_user: Dict[int, Optional[int]] = {1: None, 2: None, 3: None}

    # ---- Users ----
    def add_user(self, social_security_number:int, first_name:str, last_name:str, address:str, email:str, phone_number:str, membership_type:MembershipType) -> int:
        self._uid += 1
        uid = self._uid
        self.users[uid] = User(
            user_id=str(uid),
            ssn=social_security_number,
            first_name=first_name,
            last_name=last_name,
            address=address,
            email=email,
            phone=phone_number,
            enter_date="2030-01-01",
            membership_type=membership_type,
        )
        self.user_by_ssn[social_security_number] = uid
        return uid

    def get_user_id(self, social_security_number: int) -> int:
        uid = self.user_by_ssn.get(social_security_number)
        if uid is None:
            raise NotFoundError("No user found")
        return uid

    def get_user(self, user_id: int) -> User:
        u = self.users.get(user_id)
        if u is None:
            raise NotFoundError("No user found")
        return u

    # ---- Payments ----
    def add_payment_method(self, user_id, card_last_4, card_brand, card_exp, card_id) -> int:
        self._pid += 1
        pm = PaymentMethod(pay_id=self._pid, card_last_4=card_last_4, card_brand=card_brand, card_exp=card_exp, card_id=card_id)
        self.payment.setdefault(user_id, []).append(pm)
        return self._pid

    def get_user_payment_methods(self, user_id: int) -> List[PaymentMethod]:
        return list(self.payment.get(user_id, []))

    def bill_user(self, pay_id: int, amount: float, slot_id: Optional[int] = None) -> int:
        self._bill_id += 1
        self.bill_calls.append(BillCall(pay_id=pay_id, amount=amount, slot_id=slot_id))
        return self._bill_id

    # ---- Doctors & slots ----
    def get_available_dr_specialties(self) -> List[str]:
        return sorted({d.specialty for d in self.doctors})

    def search_doctors(self, specialty=None, min_rank=None, max_fee=None) -> List[DoctorSearchResult]:
        out = self.doctors
        if specialty:
            out = [d for d in out if d.specialty == specialty]
        if min_rank is not None:
            out = [d for d in out if d.rating >= min_rank]
        if max_fee is not None:
            out = [d for d in out if d.visit_fee <= max_fee]
        # mimic "ORDER BY rating desc"
        out = sorted(out, key=lambda d: d.rating, reverse=True)
        return out

    def search_available_appointments(self, specialty, doctor_name=None, start_date=None, end_date=None) -> List[AppointmentSlot]:
        def ok_date(s: AppointmentSlot) -> bool:
            if start_date and s.date < start_date:
                return False
            if end_date and s.date > end_date:
                return False
            return True

        out = [
            s for sid, s in self.slots.items()
            if s.specialty == specialty
            and self.slot_user[sid] is None
            and ok_date(s)
            and (doctor_name is None or doctor_name.lower() in s.dr_name.lower())
        ]
        # mimic "ORDER BY date/start_time"
        out.sort(key=lambda s: (s.date, s.start_time))
        return out[:10]

    def get_appointment_slot(self, slot_id: int) -> Optional[AppointmentSlot]:
        return self.slots.get(slot_id)

    def add_appointment(self, user_id: int, slot_id: int) -> int:
        if slot_id not in self.slots:
            raise ConflictError("Slot not available")
        if self.slot_user[slot_id] is not None:
            raise ConflictError("Slot not available")
        self.slot_user[slot_id] = user_id
        return slot_id

    def remove_appointment(self, slot_id: int) -> None:
        # idempotent cancel
        if slot_id in self.slot_user:
            self.slot_user[slot_id] = None

    def get_user_appointments(self, user_id: int) -> List[AppointmentSlot]:
        out = [self.slots[sid] for sid, uid in self.slot_user.items() if uid == user_id]
        out.sort(key=lambda s: (s.date, s.start_time))
        return out


@pytest.fixture()
def service_and_repo() -> Tuple[ClinicService, FakeRepo]:
    repo = FakeRepo()
    svc = ClinicService(repo)
    return svc, repo


def test_register_user_happy_path(service_and_repo):
    svc, repo = service_and_repo
    res = svc.register_user(
        123, "John", "Doe", "Addr", "john@e.com", "+1",
        4242, "Visa", "12/30", "tok", 10.0, MembershipType.REGULAR
    )
    assert res.user_id == 1
    assert res.pay_id == 1
    assert res.bill_id == 1
    assert repo.bill_calls == [BillCall(pay_id=1, amount=10.0, slot_id=None)]



def test_add_payment_method(service_and_repo):
    svc, _ = service_and_repo
    res = svc.register_user(
        123, "John", "Doe", "Addr", "john@e.com", "+1",
        4242, "Visa", "12/30", "tok", 10.0, MembershipType.REGULAR
    )
    pay2 = svc.add_payment_method(res.user_id, 1111, "MasterCard", "01/29", "tok2")
    assert pay2 == 2

    methods = svc.get_user_payment_methods(res.user_id)
    assert [m.pay_id for m in methods] == [1, 2]


def test_list_specialties(service_and_repo):
    svc, _ = service_and_repo
    specs = svc.list_specialties()
    assert specs == ["dermatology", "family"]


def test_search_doctors_filters(service_and_repo):
    svc, _ = service_and_repo
    # specialty filter
    fam = svc.search_doctors(specialty="family")
    assert all(d.specialty == "family" for d in fam)
    # min_rank
    high = svc.search_doctors(min_rank=4.8)
    assert all(d.rating >= 4.8 for d in high)
    # max_fee
    cheap = svc.search_doctors(max_fee=120.0)
    assert all(d.visit_fee <= 120.0 for d in cheap)
    # sorted by rating desc
    assert fam == sorted(fam, key=lambda d: d.rating, reverse=True)


def test_search_appointments_filters_and_limits(service_and_repo):
    svc, _ = service_and_repo
    slots = svc.search_appointments("family")
    assert [s.slot_id for s in slots] == [1, 2]

    slots2 = svc.search_appointments("family", doctor_name="bob")
    assert [s.slot_id for s in slots2] == [2]

    slots3 = svc.search_appointments("family", start_date="2030-01-02")
    assert [s.slot_id for s in slots3] == [2]

    slots4 = svc.search_appointments("family", end_date="2030-01-01")
    assert [s.slot_id for s in slots4] == [1]


def test_search_appointments_invalid_date(service_and_repo):
    svc, _ = service_and_repo
    with pytest.raises(ValidationError):
        svc.search_appointments("family", start_date="2030/01/01")


def test_get_slot_found_and_missing(service_and_repo):
    svc, _ = service_and_repo
    s = svc.get_slot(1)
    assert s is not None and s.slot_id == 1
    assert svc.get_slot(999) is None


def test_schedule_appointment_bills_correctly_and_returns_slot(service_and_repo):
    svc, repo = service_and_repo
    reg = svc.register_user(
        123, "John", "Doe", "Addr", "john@e.com", "+1",
        4242, "Visa", "12/30", "tok", 10.0, MembershipType.REGULAR
    )
    booked = svc.schedule_appointment(reg.user_id, reg.pay_id, 1, 100.0)
    assert booked == 1
    # second bill call is for the appointment
    assert repo.bill_calls[-1] == BillCall(pay_id=1, amount=100.0, slot_id=1)


def test_double_booking_conflict(service_and_repo):
    svc, _ = service_and_repo
    reg = svc.register_user(
        123, "John", "Doe", "Addr", "john@e.com", "+1",
        4242, "Visa", "12/30", "tok", 10.0, MembershipType.REGULAR
    )
    svc.schedule_appointment(reg.user_id, reg.pay_id, 1, 100.0)
    with pytest.raises(ConflictError):
        svc.schedule_appointment(reg.user_id, reg.pay_id, 1, 100.0)


def test_cancel_appointment_idempotent(service_and_repo):
    svc, _ = service_and_repo
    reg = svc.register_user(
        123, "John", "Doe", "Addr", "john@e.com", "+1",
        4242, "Visa", "12/30", "tok", 10.0, MembershipType.REGULAR
    )
    svc.schedule_appointment(reg.user_id, reg.pay_id, 1, 100.0)
    svc.cancel_appointment(1)
    # cancel again should not raise
    svc.cancel_appointment(1)
    assert svc.search_appointments("family")


def test_get_user_appointments(service_and_repo):
    svc, _ = service_and_repo
    reg = svc.register_user(
        123, "John", "Doe", "Addr", "john@e.com", "+1",
        4242, "Visa", "12/30", "tok", 10.0, MembershipType.REGULAR
    )
    svc.schedule_appointment(reg.user_id, reg.pay_id, 2, 150.0)
    appts = svc.get_user_appointments(reg.user_id)
    assert [a.slot_id for a in appts] == [2]


def test_get_user_id_and_get_user_not_found(service_and_repo):
    svc, _ = service_and_repo
    with pytest.raises(NotFoundError):
        svc.get_user_id(999)

    with pytest.raises(NotFoundError):
        svc.get_user(999)
