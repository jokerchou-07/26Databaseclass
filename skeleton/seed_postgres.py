"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: all inserts use ON CONFLICT DO NOTHING.
"""

import json
import os
import sys
import bcrypt
import psycopg2
from psycopg2.extras import execute_values

# ── resolve paths ────────────────────────────────────────────────────────────
SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
DATA_DIR    = os.path.join(PROJECT_DIR, "train-mock-data")

sys.path.insert(0, PROJECT_DIR)
from skeleton import config as cfg


def load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


def connect():
    return psycopg2.connect(
        host=cfg.PG_HOST,
        port=cfg.PG_PORT,
        dbname=cfg.PG_DB,
        user=cfg.PG_USER,
        password=cfg.PG_PASSWORD,
    )


def insert_many(cur, table, columns, rows):
    """Bulk insert with ON CONFLICT DO NOTHING. Returns row count inserted."""
    if not rows:
        return 0
    sql = (
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s "
        f"ON CONFLICT DO NOTHING"
    )
    execute_values(cur, sql, rows)
    return cur.rowcount


# ── seeders ──────────────────────────────────────────────────────────────────

def seed_metro_stations(cur):
    data = load("metro_stations.json")
    rows = [
        (s["station_id"], s["name"], s.get("zone", 1))
        for s in data
    ]
    n = insert_many(cur, "metro_stations", ["station_id", "name", "zone"], rows)
    print(f"  metro_stations: {n} rows")


def seed_national_rail_stations(cur):
    data = load("national_rail_stations.json")
    rows = [
        (s.get("station_id"), s.get("name"))
        for s in data
    ]
    n = insert_many(cur, "national_rail_stations", ["station_id", "name"], rows)
    print(f"  national_rail_stations: {n} rows")


def seed_metro_schedules(cur):
    data = load("metro_schedules.json")

    # 1. Insert core metro schedule master records
    schedule_rows = [
        (
            s.get("schedule_id"),
            s.get("line", "M1"),
            s.get("frequency_min", 5),
            s.get("base_fare_usd", 0.80),
            # FIX: include operating_days to satisfy NOT NULL DEFAULT constraint
            s.get("operating_days", "Daily"),
        )
        for s in data
    ]
    n1 = insert_many(
        cur, "metro_schedules",
        ["schedule_id", "line", "frequency_min", "fare", "operating_days"],
        schedule_rows
    )
    print(f"  metro_schedules: {n1} rows")

    # 2. Parse per-stop arrival times from the nested stops_in_order structure
    stop_rows = []
    for schedule in data:
        stops_list = schedule.get("stops_in_order", [])
        base_time_str = schedule.get("first_train_time", "06:00")
        base_h, base_m = map(int, base_time_str.split(":"))

        for index, station_id in enumerate(stops_list):
            travel_times = schedule.get("travel_time_from_origin_min", {})
            travel_time = travel_times.get(station_id, 0)

            # Compute HH:MM:SS arrival time string for PostgreSQL TIME type
            total_m = base_m + travel_time
            arr_h = (base_h + (total_m // 60)) % 24
            arr_m = total_m % 60
            arrival_time_str = f"{arr_h:02d}:{arr_m:02d}:00"

            stop_rows.append((
                schedule.get("schedule_id"),
                station_id,
                arrival_time_str,
                index + 1,
            ))

    n2 = insert_many(
        cur, "metro_schedule_stops",
        ["schedule_id", "station_id", "arrival_time", "stop_order"],
        stop_rows
    )
    print(f"  metro_schedule_stops: {n2} rows")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    rows = []
    for s in data:
        fare_std   = s.get("fare_classes", {}).get("standard", {}).get("base_fare_usd", 10.00)
        fare_first = s.get("fare_classes", {}).get("first", {}).get("base_fare_usd", 20.00)

        # FIX: calculate duration_min from first/last train times to satisfy DEFAULT 0 (informational)
        dep_str = s.get("first_train_time", "08:00")
        arr_str = s.get("last_train_time", "22:00")
        try:
            dep_h, dep_m = map(int, dep_str.split(":"))
            arr_h, arr_m = map(int, arr_str.split(":"))
            duration_min = (arr_h * 60 + arr_m) - (dep_h * 60 + dep_m)
            if duration_min < 0:
                duration_min = 0
        except Exception:
            duration_min = 0

        rows.append((
            s.get("schedule_id"),
            s.get("line", "NR1"),
            s.get("service_type", "normal"),
            s.get("origin_station_id"),
            s.get("destination_station_id"),
            dep_str,
            arr_str,
            duration_min,
            fare_std,
            fare_first,
            s.get("operating_days", "Daily"),
        ))
    n = insert_many(
        cur, "national_rail_schedules",
        [
            "schedule_id", "route_name", "service_type",
            "origin_station_id", "destination_station_id",
            "departure_time", "arrival_time", "duration_min",
            "fare_standard", "fare_first", "operating_days",
        ],
        rows
    )
    print(f"  national_rail_schedules: {n} rows")


def seed_national_rail_stops(cur):
    data = load("national_rail_schedules.json")
    rows = []
    for s in data:
        stops = s.get("stops_in_order", [])
        times = s.get("travel_time_from_origin_min", {})
        base_h, base_m = map(int, s.get("first_train_time", "06:00").split(":"))

        for idx, station_id in enumerate(stops):
            travel_min = times.get(station_id, 0)
            total_m = base_m + travel_min
            arr_h = (base_h + total_m // 60) % 24
            arr_m = total_m % 60
            arrival = f"{arr_h:02d}:{arr_m:02d}:00"
            rows.append((s["schedule_id"], station_id, idx + 1, arrival))

    n = insert_many(
        cur, "national_rail_schedule_stops",
        ["schedule_id", "station_id", "stop_order", "arrival_time"],
        rows
    )
    print(f"  national_rail_schedule_stops: {n} rows")


def seed_seat_layouts(cur):
    schedules_data = load("national_rail_schedules.json")
    all_schedules = [s.get("schedule_id") for s in schedules_data if s.get("schedule_id")]

    data = load("national_rail_seat_layouts.json")
    rows = []

    seeded_schedules = set()
    default_template = None

    # 1. Process natively defined layout records
    for layout in data:
        schedule_id = layout.get("schedule_id")
        if not schedule_id:
            continue

        seeded_schedules.add(schedule_id)

        if not default_template and layout.get("coaches"):
            default_template = layout.get("coaches")

        for coach_data in layout.get("coaches", []):
            coach      = coach_data.get("coach")
            fare_class = coach_data.get("fare_class")
            for seat in coach_data.get("seats", []):
                seat_num  = seat.get("seat_id")
                layout_id = f"LAYOUT_{schedule_id}_{coach}_{seat_num}"
                rows.append((layout_id, schedule_id, coach, seat_num, fare_class))

    # 2. Fallback: synthesize layouts for schedules missing from the JSON
    for sch_id in all_schedules:
        if sch_id not in seeded_schedules and default_template:
            for coach_data in default_template:
                coach      = coach_data.get("coach")
                fare_class = coach_data.get("fare_class")
                for seat in coach_data.get("seats", []):
                    seat_num  = seat.get("seat_id")
                    layout_id = f"LAYOUT_{sch_id}_{coach}_{seat_num}"
                    rows.append((layout_id, sch_id, coach, seat_num, fare_class))

    n = insert_many(
        cur, "national_rail_seat_layouts",
        ["layout_id", "schedule_id", "coach_number", "seat_number", "fare_class"],
        rows
    )
    print(f"  national_rail_seat_layouts: {n} rows")


def seed_users(cur):
    data = load("registered_users.json")
    rows = []
    for u in data:
        # Split name into first/surname components
        user_name = u.get("name") or u.get("full_name") or u.get("first_name") or "Unknown User"
        parts = user_name.split(" ", 1)
        first_name = parts[0]
        surname    = parts[1] if len(parts) > 1 else ""

        year_of_birth   = u.get("year_of_birth") or 1990
        secret_question = u.get("secret_question") or "What is your favorite color?"
        secret_answer   = u.get("secret_answer") or "Blue"

        # Hash with bcrypt — never store plain-text passwords
        original_password = u.get("password", "default_pass")
        hashed_password = bcrypt.hashpw(
            original_password.encode('utf-8'), bcrypt.gensalt()
        ).decode('utf-8')

        rows.append((
            u.get("user_id"),
            first_name,
            surname,
            year_of_birth,
            u.get("email"),
            hashed_password,
            secret_question,
            secret_answer,
        ))

    n = insert_many(
        cur, "users",
        ["user_id", "first_name", "surname", "year_of_birth",
         "email", "password", "secret_question", "secret_answer"],
        rows
    )
    print(f"  users: {n} rows")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    rows = []

    for b in data:
        # Normalise non-standard 'completed' → 'confirmed'
        raw_status = b.get("status", "confirmed").lower()
        if raw_status == "completed":
            final_status = "confirmed"
        elif raw_status not in ['confirmed', 'cancelled', 'refunded']:
            final_status = "confirmed"
        else:
            final_status = raw_status

        rows.append((
            b.get("booking_id"),
            b.get("user_id"),
            b.get("schedule_id", "NR_SCH01"),
            b.get("origin_station_id"),
            b.get("destination_station_id"),
            b.get("travel_date"),
            b.get("departure_time", "07:00:00"),
            b.get("carriage_number", "A"),
            b.get("seat_number", "1A"),
            b.get("amount_usd", 0.0),
            final_status,
        ))

    n = insert_many(
        cur, "bookings",
        [
            "booking_id", "user_id", "schedule_id",
            "origin_station_id", "destination_station_id",
            "travel_date", "departure_time", "carriage_number",
            "seat_number", "amount_usd", "status",
        ],
        rows
    )
    print(f"  bookings: {n} rows")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    rows = []

    for t in data:
        entry_time = t.get("entry_time", "2026-05-28 08:00:00")

        # Derive travel_date from entry_time if not explicitly provided
        travel_date = t.get("travel_date")
        if not travel_date and entry_time:
            travel_date = entry_time.split(" ")[0]

        # Handle alternative field names across different JSON formats
        history_id    = t.get("history_id") or t.get("trip_id")
        entry_station = t.get("entry_station_id") or t.get("origin_station_id")
        exit_station  = t.get("exit_station_id") or t.get("destination_station_id")
        fare          = t.get("fare") or t.get("amount_usd") or 0.0

        rows.append((
            history_id,
            t.get("user_id"),
            t.get("schedule_id"),
            entry_station,
            exit_station,
            travel_date,
            entry_time,
            t.get("exit_time"),
            t.get("ticket_type", "Single Ticket"),
            fare,
        ))

    n = insert_many(
        cur, "metro_travel_history",
        [
            "history_id", "user_id", "schedule_id",
            "entry_station_id", "exit_station_id",
            "travel_date", "entry_time", "exit_time",
            "ticket_type", "fare",
        ],
        rows
    )
    print(f"  metro_travel_history: {n} rows")


def seed_payments(cur):
    data = load("payments.json")
    rows = []
    for p in data:
        raw_target_id = p.get("booking_id") or p.get("trip_id") or p.get("history_id")

        b_id     = None
        h_id     = None
        ref_type = "national_rail"

        if raw_target_id:
            if raw_target_id.startswith("BK") or raw_target_id.startswith("NR"):
                b_id     = raw_target_id
                ref_type = "national_rail"
            elif raw_target_id.startswith("MT"):
                h_id     = raw_target_id
                ref_type = "metro"

        # Normalise 'paid' → 'success'
        raw_status = (p.get("status") or p.get("payment_status") or "paid").lower()
        if raw_status == "paid":
            final_status = "success"
        elif raw_status not in ["success", "failed", "refunded"]:
            final_status = "success"
        else:
            final_status = raw_status

        amount = p.get("amount_usd") or p.get("amount") or 0.00

        rows.append((
            p.get("payment_id"),
            p.get("user_id"),
            b_id,
            h_id,
            ref_type,
            amount,
            p.get("payment_method", "credit_card"),
            final_status,
        ))

    n = insert_many(
        cur, "payments",
        ["payment_id", "user_id", "booking_id", "history_id",
         "reference_type", "amount_usd", "payment_method", "status"],
        rows
    )
    print(f"  payments: {n} rows")


def seed_feedback(cur):
    data = load("feedback.json")
    rows = []
    for f in data:
        raw_booking_id = f.get("booking_id")

        # The feedback JSON sometimes references metro trip IDs (e.g. "MT001")
        # instead of national rail booking IDs. Since the feedback.booking_id FK
        # points to the bookings table (national rail only), we must set those
        # to NULL rather than inserting an invalid reference.
        if raw_booking_id and raw_booking_id.upper().startswith("MT"):
            booking_id = None
        else:
            booking_id = raw_booking_id

        rows.append((
            f.get("feedback_id"),
            f.get("user_id"),
            booking_id,
            f.get("rating"),
            f.get("comment"),
        ))
    n = insert_many(
        cur, "feedback",
        ["feedback_id", "user_id", "booking_id", "rating", "comments"],
        rows
    )
    print(f"  feedback: {n} rows")


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print("Connecting to PostgreSQL...")
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()

    try:
        print("Seeding tables (dependency order):")
        seed_metro_stations(cur)
        seed_national_rail_stations(cur)
        seed_metro_schedules(cur)
        seed_national_rail_schedules(cur)
        seed_national_rail_stops(cur)
        seed_seat_layouts(cur)
        seed_users(cur)
        seed_national_rail_bookings(cur)
        seed_metro_travels(cur)
        seed_payments(cur)
        seed_feedback(cur)
        conn.commit()
        print("\nAll done. Database seeded successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
