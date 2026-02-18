import sqlite3

import pytest

from clinic_mcp_server.domain.enums import MembershipType
from clinic_mcp_server.domain.errors import (
    ConflictError,
    NotFoundError,
    ValidationError,
)
from clinic_mcp_server.infra.sqlite_repo import SQLiteClinicRepository
from clinic_mcp_server.services.clinic_service import ClinicService


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "clinic_integration.db"


@pytest.fixture()
def repo(db_path):
    repo =  SQLiteClinicRepository(str(db_path))
    repo.init_schema()
    return repo


@pytest.fixture()
def svc(repo):
    return ClinicService(repo)


def _raw_conn(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("PRAGMA foreign_keys = ON;")
    return conn, cur




def _register_user(svc: ClinicService, ssn: int, first="A", last="B", amount=10.0, membership="regular"):
    return svc.register_user(
        ssn,
        first,
        last,
        "Addr",
        f"{first.lower()}@e.com",
        "+49",
        1111,
        "Visa",
        "12/30",
        f"tok_{ssn}",
        amount,
        MembershipType(membership),
    )


def test_db_initializes_and_seeds(repo, db_path):
    # touch repo by calling something
    # srv = ClinicService(repo)
    specs = ClinicService(repo).list_specialties()
    assert specs, "expected seeded specialties"

    conn, cur = _raw_conn(db_path)
    try:
        # tables exist
        for table in ["users", "doctors", "doctor_opening_days", "payment_methods", "slots", "bills"]:
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
            assert cur.fetchone() is not None, f"missing table {table}"

        # seeded doctors and slots exist
        cur.execute("SELECT COUNT(*) AS c FROM doctors")
        assert cur.fetchone()["c"] > 0

        cur.execute("SELECT COUNT(*) AS c FROM slots")
        assert cur.fetchone()["c"] > 0
    finally:
        conn.close()


def test_fk_enforced(repo, db_path):
    # verify PRAGMA foreign_keys is on for the underlying DB connections.
    # We can't directly read repo's connection, so we do a behavior check:
    # inserting a payment method with non-existing user_id should fail.
    repo.init_schema()
    conn, cur = _raw_conn(db_path)
    try:
        # If FK is enforced, this insert should fail
        with pytest.raises(sqlite3.IntegrityError):
            cur.execute(
                "INSERT INTO payment_methods (user_id, card_last_4, card_brand, card_exp, card_id) VALUES (?, ?, ?, ?, ?)",
                (999999, 1234, "Visa", "12/30", "tok_bad"),
            )
            conn.commit()
    finally:
        conn.close()


def test_register_user_readback_and_payment_methods(svc, db_path):
    reg = _register_user(svc, 111222333, first="Alice", membership="gold")

    u = svc.get_user(reg.user_id)
    assert u.first_name == "Alice"
    assert u.membership_type == "gold"

    # payment method created
    methods = svc.get_user_payment_methods(reg.user_id)
    assert len(methods) == 1
    assert methods[0].card_last_4 == 1111

    # add second payment method
    pay2 = svc.add_payment_method(reg.user_id, 2222, "MasterCard", "01/29", "tok2")
    methods2 = svc.get_user_payment_methods(reg.user_id)
    assert len(methods2) == 2
    assert {m.pay_id for m in methods2} == {reg.pay_id, pay2}

    # bills inserted: initial registration bill
    conn, cur = _raw_conn(db_path)
    try:
        cur.execute("SELECT COUNT(*) AS c FROM bills WHERE pay_id=?", (reg.pay_id,))
        assert cur.fetchone()["c"] >= 1
    finally:
        conn.close()


def test_get_user_id_not_found_and_get_user_not_found(svc):
    with pytest.raises(NotFoundError):
        svc.get_user_id(999999999)

    with pytest.raises(NotFoundError):
        svc.get_user(999999)


def test_doctor_search_filters(svc):
    # no filters
    all_docs = svc.search_doctors()
    assert all_docs and len(all_docs) >= 1

    # specialty filter
    fam = svc.search_doctors(specialty="family")
    assert fam
    assert all(d.specialty == "family" for d in fam)

    # min_rank filter (should still return some, depending on seed)
    high = svc.search_doctors(min_rank=4.7)
    assert all(d.rating >= 4.7 for d in high)

    # max_fee filter
    cheap = svc.search_doctors(max_fee=120.0)
    assert all(d.visit_fee <= 120.0 for d in cheap)


def test_search_appointments_filters_and_slot_lookup(svc):
    # baseline
    slots = svc.search_appointments("family")
    assert slots
    s0 = slots[0]

    # slot lookup found
    found = svc.get_slot(s0.slot_id)
    assert found is not None
    assert found.slot_id == s0.slot_id

    # slot lookup missing
    assert svc.get_slot(999999) is None

    # doctor_name filter should narrow to something (seed uses "Dr. ...")
    name_filtered = svc.search_appointments("family", doctor_name="Dr.")
    assert name_filtered

    # start_date/end_date filters (pick dates from existing slot)
    # We don't know exact seeded dates; use the first slot date as anchor.
    anchor = s0.date
    by_start = svc.search_appointments("family", start_date=anchor)
    assert by_start  # should include anchor day and after

    by_end = svc.search_appointments("family", end_date=anchor)
    assert by_end  # should include anchor day and before

    # invalid date format should raise ValidationError
    with pytest.raises(ValidationError):
        svc.search_appointments("family", start_date="2026/01/01")


def test_booking_flow_bills_and_prevents_double_booking(svc, db_path):
    reg = _register_user(svc, 222333444, first="Bob")

    slots = svc.search_appointments("family")
    assert slots
    slot_id = slots[0].slot_id
    fee = slots[0].visit_fee

    booked = svc.schedule_appointment(reg.user_id, reg.pay_id, slot_id, fee)
    assert booked == slot_id

    # user appointments now includes it
    appts = svc.get_user_appointments(reg.user_id)
    assert any(a.slot_id == slot_id for a in appts)

    # double booking should fail (ConflictError)
    with pytest.raises(ConflictError):
        svc.schedule_appointment(reg.user_id, reg.pay_id, slot_id, fee)

    # bills should include appointment bill with slot_id set
    conn, cur = _raw_conn(db_path)
    try:
        cur.execute("SELECT COUNT(*) AS c FROM bills WHERE pay_id=? AND slot_id=?", (reg.pay_id, slot_id))
        assert cur.fetchone()["c"] == 1
    finally:
        conn.close()


def test_cancel_then_rebook(svc):
    reg = _register_user(svc, 333444555, first="Carl")

    slots = svc.search_appointments("family")
    assert slots
    slot_id = slots[0].slot_id
    fee = slots[0].visit_fee

    svc.schedule_appointment(reg.user_id, reg.pay_id, slot_id, fee)
    svc.cancel_appointment(slot_id)

    # should be removable again without error (idempotent cancel)
    svc.cancel_appointment(slot_id)

    # should now be bookable again
    svc.schedule_appointment(reg.user_id, reg.pay_id, slot_id, fee)


def test_booking_nonexistent_slot_fails(svc):
    reg = _register_user(svc, 444555666, first="Dana")

    with pytest.raises(ConflictError):
        svc.schedule_appointment(reg.user_id, reg.pay_id, 999999, 100.0)


def test_membership_validation_surfaces(svc):
    with pytest.raises(ValidationError):
        svc.register_user(
            555666777,
            "Eve",
            "Bad",
            "Addr",
            "eve@e.com",
            "+49",
            1111,
            "Visa",
            "12/30",
            "tok_bad",
            10.0,
            "platinum",
        )
