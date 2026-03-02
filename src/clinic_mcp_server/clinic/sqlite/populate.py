from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from clinic_mcp_server.clinic.sqlite.db import SQLiteClinicDB


def populate_repo(db: SQLiteClinicDB) -> None:
    """Seed doctors, their schedules, appointment slots, and demo users into the database."""
    _add_doctors(db)
    _add_slots(db)
    _add_users(db)
    db.conn.commit()


def _add_doctors(db: SQLiteClinicDB) -> None:
    doctors = [
        ("Dr. Alice Green", 30, 150, "family", 4.7),
        ("Dr. Bob Taylor", 20, 100, "family", 4.5),
        ("Dr. Carol Smith", 25, 150, "family", 4.6),
        ("Dr. David Lee", 30, 200, "family", 4.8),
        ("Dr. Eva Clark", 20, 100, "family", 4.4),
        ("Dr. Fiona White", 20, 200, "pediatrics", 4.9),
        ("Dr. George Young", 30, 150, "pediatrics", 4.7),
        ("Dr. Helen King", 25, 150, "pediatrics", 4.6),
        ("Dr. Ian Black", 30, 200, "dermatology", 4.8),
        ("Dr. Julia Adams", 20, 100, "dermatology", 4.5),
    ]

    default_schedule = [
        (0, "09:00", "13:00"),  # Monday
        (2, "09:00", "13:00"),  # Wednesday
    ]

    for doc in doctors:
        db.cursor.execute(
            "INSERT INTO doctors (dr_name, slot_visiting_time, visit_fee, specialty, rating) VALUES (?, ?, ?, ?, ?)",
            doc,
        )
        dr_id = db.cursor.lastrowid

        for weekday, start_time, end_time in default_schedule:
            db.cursor.execute(
                "INSERT INTO doctor_opening_days (dr_id, weekday, start_time, end_time) VALUES (?, ?, ?, ?)",
                (dr_id, weekday, start_time, end_time),
            )


def _add_slots(db: SQLiteClinicDB, days_range: int = 30, from_date: date | None = None) -> None:
    if from_date is None:
        from_date = datetime.today().date()

    db.cursor.execute("""
        SELECT d.dr_id, d.slot_visiting_time, od.weekday, od.start_time, od.end_time
        FROM doctors d
        JOIN doctor_opening_days od ON d.dr_id = od.dr_id
    """)
    schedule = db.cursor.fetchall()

    for row in schedule:
        dr_id = row["dr_id"]
        slot_minutes = row["slot_visiting_time"]
        weekday = row["weekday"]
        start_str = row["start_time"]
        end_str = row["end_time"]

        for day_offset in range(days_range):
            slot_date = from_date + timedelta(days=day_offset)
            if slot_date.weekday() != weekday:
                continue

            slot_duration = timedelta(minutes=slot_minutes)
            start_dt = datetime.strptime(f"{slot_date} {start_str}", "%Y-%m-%d %H:%M")
            end_dt = datetime.strptime(f"{slot_date} {end_str}", "%Y-%m-%d %H:%M")

            while start_dt + slot_duration <= end_dt:
                db.cursor.execute("""
                    INSERT INTO slots (dr_id, date, start_time, end_time)
                    VALUES (?, ?, ?, ?)
                """, (
                    dr_id,
                    slot_date.isoformat(),
                    start_dt.strftime("%H:%M"),
                    (start_dt + slot_duration).strftime("%H:%M"),
                ))
                start_dt += slot_duration

def _add_users(db: SQLiteClinicDB) -> None:
    """Seed a small set of demo users with payment methods and an initial membership bill."""
    today = date.today().isoformat()

    users = [
        # (ssn, first_name, last_name, address, email, phone, membership_type)
        (100000001, "Alice", "Johnson", "12 Oak Street, Springfield", "alice.johnson@example.com", "+1-555-0101", "regular"),
        (100000002, "Bob", "Martinez", "34 Maple Ave, Shelbyville", "bob.martinez@example.com", "+1-555-0102", "silver"),
        (100000003, "Carol", "Williams", "56 Pine Road, Capital City", "carol.williams@example.com", "+1-555-0103", "gold"),
    ]

    payment_methods = [
        # (card_last_4, card_brand, card_exp, card_id, amount)
        (4242, "visa",       "12/28", "tok_alice_visa",   50.0),
        (5555, "mastercard", "06/27", "tok_bob_mc",       75.0),
        (3782, "amex",       "09/29", "tok_carol_amex",  100.0),
    ]

    for (ssn, first, last, address, email, phone, membership), (last4, brand, exp, card_id, amount) in zip(users, payment_methods):
        db.cursor.execute(
            """
            INSERT INTO users (social_security_number, first_name, last_name, address, email, phone, enter_date, membership_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ssn, first, last, address, email, phone, today, membership),
        )
        user_id = db.cursor.lastrowid

        db.cursor.execute(
            """
            INSERT INTO payment_methods (user_id, card_last_4, card_brand, card_exp, card_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, last4, brand, exp, card_id),
        )
        pay_id = db.cursor.lastrowid

        # initial membership bill
        db.cursor.execute(
            """
            INSERT INTO bills (pay_id, date, amount)
            VALUES (?, ?, ?)
            """,
            (pay_id, datetime.now().isoformat(timespec="seconds"), amount),
        )


# Made with Bob