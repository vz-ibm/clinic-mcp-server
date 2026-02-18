import os
import sqlite3
from datetime import date, datetime, timedelta

from pydantic import BaseModel, Field

from clinic_mcp_server.domain.enums import MembershipType


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


class ClinicDB:
    def __init__(self, db_path: str):
            self.db_path = db_path

            directory = os.path.dirname(self.db_path)
            if directory:
                os.makedirs(directory, exist_ok=True)

            # Open connection (no schema side effects here)
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            self.cursor = self.conn.cursor()

            # Enforce FK constraints in SQLite (per-connection setting)
            self.cursor.execute("PRAGMA foreign_keys = ON;")


    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def __enter__(self) -> "ClinicDB":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
    
    def init_schema(self, *, seed: bool = True) -> None:
        """
        Ensure schema exists. Safe to call multiple times.
        Optionally seed initial data if DB is empty.
        """
        self.create_tables()
        if seed:
            self.seed_if_empty()
        self.conn.commit()


    def reset_schema(self, *, seed: bool = True) -> None:
        # drop in FK-safe order
        self.cursor.execute("PRAGMA foreign_keys = OFF;")
        self.cursor.execute("DROP TABLE IF EXISTS bills;")
        self.cursor.execute("DROP TABLE IF EXISTS slots;")
        self.cursor.execute("DROP TABLE IF EXISTS payment_methods;")
        self.cursor.execute("DROP TABLE IF EXISTS doctor_opening_days;")
        self.cursor.execute("DROP TABLE IF EXISTS doctors;")
        self.cursor.execute("DROP TABLE IF EXISTS users;")
        self.cursor.execute("PRAGMA foreign_keys = ON;")

        self.create_tables()
        if seed:
            self.seed_if_empty()
        self.conn.commit()  

    def seed_if_empty(self) -> None:
        """
        Seed doctors + slots only if there are no doctors.
        Idempotent: calling multiple times won't duplicate data.
        """
        self.cursor.execute("SELECT COUNT(*) AS c FROM doctors")
        if int(self.cursor.fetchone()["c"]) > 0:
            return

        self.add_doctors()
        self.add_slots()    

    def create_tables(self):
        # Safer table creation order for FK relationships
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            social_security_number INTEGER,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            address TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            enter_date DATETIME NOT NULL,
            membership_type TEXT CHECK (membership_type IN ('regular', 'gold', 'silver'))
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctors (
            dr_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dr_name TEXT,
            slot_visiting_time INTEGER,
            visit_fee REAL,
            specialty TEXT,
            rating REAL
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS doctor_opening_days (
            dr_id INTEGER,
            weekday INTEGER,  -- 0 = Monday, 6 = Sunday
            start_time TEXT,  -- "09:00"
            end_time TEXT,    -- "17:00"
            FOREIGN KEY (dr_id) REFERENCES doctors(dr_id)
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS payment_methods (
            pay_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            card_last_4 INTEGER NOT NULL,
            card_brand TEXT NOT NULL,
            card_exp TEXT NOT NULL,
            card_id TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS slots (
            slot_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dr_id INTEGER NOT NULL,
            user_id INTEGER DEFAULT NULL,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            placeholder DATETIME DEFAULT NULL,
            FOREIGN KEY (dr_id) REFERENCES doctors(dr_id),
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        )
        """)

        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
            pay_id INTEGER NOT NULL,
            slot_id INTEGER,
            date DATETIME NOT NULL,
            amount REAL NOT NULL,
            FOREIGN KEY (pay_id) REFERENCES payment_methods(pay_id),
            FOREIGN KEY (slot_id) REFERENCES slots(slot_id)
        )
        """)

    def remove_db(self):
        self.close()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
            print("Database deleted.")
        else:
            print("Database file not found.")

    def add_doctors(self):
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
            self.cursor.execute(
                "INSERT INTO doctors (dr_name, slot_visiting_time, visit_fee, specialty, rating) VALUES (?, ?, ?, ?, ?)",
                doc,
            )
            dr_id = self.cursor.lastrowid

            for weekday, start_time, end_time in default_schedule:
                self.cursor.execute(
                    "INSERT INTO doctor_opening_days (dr_id, weekday, start_time, end_time) VALUES (?, ?, ?, ?)",
                    (dr_id, weekday, start_time, end_time),
                )

    def add_slots(self, days_range: int = 30, from_date: date | None = None):
        if from_date is None:
            from_date = datetime.today().date()

        self.cursor.execute("""
            SELECT d.dr_id, d.slot_visiting_time, od.weekday, od.start_time, od.end_time
            FROM doctors d
            JOIN doctor_opening_days od ON d.dr_id = od.dr_id
        """)
        schedule = self.cursor.fetchall()

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
                    self.cursor.execute("""
                        INSERT INTO slots (dr_id, date, start_time, end_time)
                        VALUES (?, ?, ?, ?)
                    """, (
                        dr_id,
                        slot_date.isoformat(),
                        start_dt.strftime("%H:%M"),
                        (start_dt + slot_duration).strftime("%H:%M"),
                    ))
                    start_dt += slot_duration

        self.conn.commit()

    def _require_lastrowid(self) -> int:
        rowid = self.cursor.lastrowid
        if rowid is None:
            raise RuntimeError("SQLite lastrowid is None (insert may have failed).")
        return int(rowid)

    def add_user(
        self,
        social_security_number: int,
        first_name: str,
        last_name: str,
        address: str,
        email: str,
        phone_number: str,
        membership_type: MembershipType = MembershipType.REGULAR,
    ) -> int:
        if membership_type not in ["regular", "gold", "silver"]:
            raise ValueError("Invalid membership_type. Choose from 'regular', 'gold', 'silver'.")

        today = date.today().isoformat()
        self.cursor.execute(
            """
            INSERT INTO users (social_security_number, first_name, last_name, address, email, phone, enter_date, membership_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (social_security_number, first_name, last_name, address, email, phone_number, today, membership_type.value),
        )
        self.conn.commit()
        return self._require_lastrowid()

    def bill_user(self, pay_id: int, amount: float, slot_id: int | None = None) -> int:
        now = datetime.now().isoformat(timespec="seconds")
        if slot_id is None:
            self.cursor.execute(
                """
                INSERT INTO bills (pay_id, date, amount)
                VALUES (?, ?, ?)
                """,
                (pay_id, now, amount),
            )
        else:
            self.cursor.execute(
                """
                INSERT INTO bills (pay_id, slot_id, date, amount)
                VALUES (?, ?, ?, ?)
                """,
                (pay_id, slot_id, now, amount),
            )
        self.conn.commit()
        return self._require_lastrowid()

    def add_payment_method(
        self,
        user_id: int,
        card_last_4: int,
        card_brand: str,
        card_exp: str,
        card_id: str,
    ) -> int:
        self.cursor.execute(
            """
            INSERT INTO payment_methods (user_id, card_last_4, card_brand, card_exp, card_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, card_last_4, card_brand, card_exp, card_id),
        )
        self.conn.commit()
        return self._require_lastrowid()

    def add_appointment(self, user_id: int, slot_id: int) -> int:
        # prevent double booking
        self.cursor.execute("""
            UPDATE slots
            SET user_id = ?
            WHERE slot_id = ?
              AND user_id IS NULL
        """, (user_id, slot_id))
        self.conn.commit()

        if self.cursor.rowcount != 1:
            raise ValueError(f"Slot {slot_id} is not available (already booked or does not exist).")

        return slot_id

    def remove_appointment(self, slot_id: int) -> None:
        self.cursor.execute("""
            UPDATE slots
            SET user_id = NULL
            WHERE slot_id = ?
        """, (int(slot_id),))
        self.conn.commit()

    def get_available_dr_specialties(self) -> list[str]:
        self.cursor.execute("""
            SELECT DISTINCT specialty
            FROM doctors
            WHERE specialty IS NOT NULL
            ORDER BY specialty COLLATE NOCASE
        """)
        return [row[0] for row in self.cursor.fetchall()]

    def search_doctors(
        self,
        specialty: str | None = None,
        min_rank: float | None = None,
        max_fee: float | None = None,
    ) -> list[DoctorSearchResult]:
        query = """
            SELECT
                d.dr_id,
                d.dr_name,
                d.specialty,
                d.rating,
                d.visit_fee,
                (
                    SELECT MIN(s.date || ' ' || s.start_time)
                    FROM slots s
                    WHERE s.dr_id = d.dr_id
                      AND s.user_id IS NULL
                      AND datetime(s.date || ' ' || s.start_time) >= datetime('now')
                ) AS next_available_appointment
            FROM doctors d
            WHERE 1=1
        """
        params: list[object] = []

        if specialty:
            query += " AND d.specialty = ?"
            params.append(specialty)

        if min_rank is not None:
            query += " AND d.rating >= ?"
            params.append(min_rank)

        if max_fee is not None:
            query += " AND d.visit_fee <= ?"
            params.append(max_fee)

        query += " ORDER BY d.rating DESC"

        self.cursor.execute(query, params)
        rows = self.cursor.fetchall()

        out: list[DoctorSearchResult] = []
        for r in rows:
            out.append(
                DoctorSearchResult(
                    dr_id=int(r[0]),
                    dr_name=str(r[1]),
                    specialty=str(r[2]),
                    rating=float(r[3]),
                    visit_fee=float(r[4]),
                    next_available_appointment=r[5],
                )
            )
        return out

    def search_available_appointments(
        self,
        specialty: str,
        doctor_name: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> list[AppointmentSlot]:
        base_query = """
            SELECT
                s.slot_id,
                d.dr_name,
                d.specialty,
                s.date,
                s.start_time,
                s.end_time,
                d.visit_fee,
                d.rating
            FROM slots s
            JOIN doctors d ON s.dr_id = d.dr_id
            WHERE d.specialty = ?
              AND s.user_id IS NULL
              AND date(s.date) >= date('now')
        """
        params: list[object] = [specialty]

        if doctor_name:
            base_query += " AND d.dr_name LIKE ?"
            params.append(f"%{doctor_name}%")

        if start_date:
            base_query += " AND date(s.date) >= date(?)"
            params.append(start_date)

        if end_date:
            base_query += " AND date(s.date) <= date(?)"
            params.append(end_date)

        base_query += " ORDER BY s.date ASC, s.start_time ASC LIMIT 10"

        self.cursor.execute(base_query, params)
        rows = self.cursor.fetchall()

        return [
            AppointmentSlot(
                slot_id=int(r[0]),
                dr_name=str(r[1]),
                specialty=str(r[2]),
                date=str(r[3]),
                start_time=str(r[4]),
                end_time=str(r[5]),
                visit_fee=float(r[6]),
                rating=float(r[7]),
            )
            for r in rows
        ]

    def get_user_payment_methods(self, user_id: int) -> list[PaymentMethod]:
        self.cursor.execute("""
            SELECT pay_id, card_last_4, card_brand, card_exp, card_id
            FROM payment_methods
            WHERE user_id = ?
            ORDER BY pay_id ASC
        """, (user_id,))
        rows = self.cursor.fetchall()
        return [
            PaymentMethod(
                pay_id=int(r[0]),
                card_last_4=int(r[1]),
                card_brand=str(r[2]),
                card_exp=str(r[3]),
                card_id=str(r[4]),
            )
            for r in rows
        ]

    def get_user_id(self, social_security_number: int) -> int:
        self.cursor.execute("""
            SELECT user_id
            FROM users
            WHERE social_security_number = ?
        """, (social_security_number,))
        row = self.cursor.fetchone()
        if not row:
            raise ValueError(f"No user found with social security number: {social_security_number}")
        return int(row[0])

    def get_user(self, user_id: int) -> User:
        self.cursor.execute("""
            SELECT
                u.user_id,
                u.social_security_number,
                u.first_name,
                u.last_name,
                u.address,
                u.email,
                u.phone,
                u.enter_date,
                u.membership_type
            FROM users u
            WHERE u.user_id = ?
        """, (user_id,))
        r = self.cursor.fetchone()
        if not r:
            raise ValueError(f"No user found with id: {user_id}")

        return User(
            user_id=str(r[0]),
            ssn=int(r[1]),
            first_name=str(r[2]),
            last_name=str(r[3]),
            address=str(r[4]),
            email=str(r[5]),
            phone=str(r[6]),
            enter_date=str(r[7]),
            membership_type=MembershipType(r[8]),
        )

    def get_user_appointments(self, user_id: int) -> list[AppointmentSlot]:
        self.cursor.execute("""
            SELECT
                s.slot_id,
                d.dr_name,
                d.specialty,
                s.date,
                s.start_time,
                s.end_time,
                d.visit_fee,
                d.rating
            FROM slots s
            JOIN doctors d ON s.dr_id = d.dr_id
            WHERE s.user_id = ?
            ORDER BY s.date ASC, s.start_time ASC
        """, (user_id,))
        rows = self.cursor.fetchall()
        return [
            AppointmentSlot(
                slot_id=int(r[0]),
                dr_name=str(r[1]),
                specialty=str(r[2]),
                date=str(r[3]),
                start_time=str(r[4]),
                end_time=str(r[5]),
                visit_fee=float(r[6]),
                rating=float(r[7]),
            )
            for r in rows
        ]

    def get_appointment_slot(self, slot_id: int) -> AppointmentSlot | None:
        self.cursor.execute("""
            SELECT
                s.slot_id,
                d.dr_name,
                d.specialty,
                s.date,
                s.start_time,
                s.end_time,
                d.visit_fee,
                d.rating
            FROM slots s
            JOIN doctors d ON s.dr_id = d.dr_id
            WHERE s.slot_id = ?
        """, (slot_id,))
        r = self.cursor.fetchone()
        if not r:
            return None

        return AppointmentSlot(
            slot_id=int(r[0]),
            dr_name=str(r[1]),
            specialty=str(r[2]),
            date=str(r[3]),
            start_time=str(r[4]),
            end_time=str(r[5]),
            visit_fee=float(r[6]),
            rating=float(r[7]),
        )
