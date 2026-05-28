"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
import os
import sys

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
        (s["station_id"], s["name"], s.get("zone", 1)) # 確保把資料轉成 tuple
        for s in data
    ]
    # 這裡的表名和欄位名稱，必須跟你的 schema.sql 100% 一致！
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
    schedule_rows = [
        (s.get("schedule_id"), s.get("line", "M1"), 5, 2.50) 
        for s in data
    ]
    n1 = insert_many(cur, "metro_schedules", ["schedule_id", "line", "frequency_min", "fare"], schedule_rows)
    print(f"  metro_schedules: {n1} rows")

    stop_rows = []
    for schedule in data:
        for stop in schedule.get("stops", []):
            stop_rows.append((
                schedule.get("schedule_id"),
                stop.get("station_id"),
                stop.get("arrival_time"),
                stop.get("stop_order")
            ))
    n2 = insert_many(cur, "metro_schedule_stops", 
                    ["schedule_id", "station_id", "arrival_time", "stop_order"], stop_rows)
    print(f"  metro_schedule_stops: {n2} rows")


def seed_national_rail_schedules(cur):
    data = load("national_rail_schedules.json")
    rows = [
        (
            s.get("schedule_id"), 
            "NR1", 
            "Normal", 
            s.get("origin_station_id"), 
            s.get("destination_station_id"), 
            s.get("departure_time", "08:00"), # 加上 departure_time 預設值
            s.get("arrival_time", "10:00"),   # 加上 arrival_time 預設值
            10.00, 
            20.00  
        )
        for s in data
    ]
    n = insert_many(cur, "national_rail_schedules", 
                    ["schedule_id", "route_name", "service_type", "origin_station_id", "destination_station_id", "departure_time", "arrival_time", "fare_standard", "fare_first"], rows)
    print(f"  national_rail_schedules: {n} rows")


def seed_seat_layouts(cur):
    data = load("national_rail_seat_layouts.json")
    rows = []
    for layout in data:
        schedule_id = layout.get("schedule_id")
        for seat in layout.get("seats", []):
            coach = seat.get("coach")
            seat_num = seat.get("seat_number")
            layout_id = f"LAYOUT_{schedule_id}_{coach}_{seat_num}"
            rows.append((
                layout_id,
                schedule_id,
                coach,
                seat_num,
                seat.get("fare_class")
            ))
    n = insert_many(cur, "national_rail_seat_layouts", 
                    ["layout_id", "schedule_id", "coach_number", "seat_number", "fare_class"], rows)
    print(f"  national_rail_seat_layouts: {n} rows")


def seed_users(cur):
    data = load("registered_users.json")
    rows = []
    for u in data:
        # 嘗試抓取 "name"，如果沒有，試試看 "full_name"，再沒有就給預設值
        user_name = u.get("name") or u.get("full_name") or u.get("first_name") or "Unknown User"
        
        rows.append((
            u.get("user_id"), 
            user_name, 
            u.get("email"), 
            "default_pass"
        ))
        
    n = insert_many(cur, "users", ["user_id", "name", "email", "password"], rows)
    print(f"  users: {n} rows")


def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    rows = [
        (
            b.get("booking_id"), 
            b.get("user_id"), 
            "NR_SCH01", 
            b.get("travel_date"), 
            "07:00",    
            "A",        
            "1A",       
            b.get("amount_usd"), 
            b.get("status")
        )
        for b in data
    ]
    n = insert_many(cur,"national_rail_bookings",
                    ["booking_id", "user_id", "schedule_id", "travel_date", "departure_time", "carriage_number", "seat_number", "amount_usd", "status"], rows)
    print(f"  bookings: {n} rows")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json")
    rows = []
    for t in data:
        # 嘗試抓取各種可能的鍵值名稱，如果真的都沒有，就給預設的時間與票價
        entry_time = t.get("tap_in_time") or t.get("entry_time") or "2026-05-28 08:00:00+00"
        exit_time = t.get("tap_out_time") or t.get("exit_time") or "2026-05-28 08:30:00+00"
        fare = t.get("fare_usd") or t.get("fare") or 2.50
        
        rows.append((
            t.get("trip_id") or t.get("history_id"), 
            t.get("user_id"), 
            t.get("origin_station_id") or t.get("entry_station_id"), 
            t.get("destination_station_id") or t.get("exit_station_id"), 
            entry_time, 
            exit_time, 
            fare
        ))
        
    n = insert_many(cur, "metro_travel_history", 
                    ["history_id", "user_id", "entry_station_id", "exit_station_id", "entry_time", "exit_time", "fare"], rows)
    print(f"  metro_travel_history: {n} rows")


def seed_payments(cur):
    data = load("payments.json")
    rows = []
    for p in data:
        status = p.get("status") or p.get("payment_status") or "paid"
        amount = p.get("amount_usd") or p.get("amount") or 0.00
        
        # 抓出目標 ID (可能是 booking_id, trip_id 或 history_id)
        raw_target_id = p.get("booking_id") or p.get("trip_id") or p.get("history_id")
        
        # 智慧分流：根據前綴字元決定放進哪一個外鍵欄位
        b_id = None
        h_id = None
        if raw_target_id:
            if raw_target_id.startswith("BK"):
                b_id = raw_target_id
            elif raw_target_id.startswith("MT"):
                h_id = raw_target_id

        rows.append((
            p.get("payment_id"), 
            b_id,   # 只有 BK 開頭才會寫入這欄
            h_id,   # 只有 MT 開頭才會寫入這欄
            amount, 
            "credit_card",       
            status
        ))
        
    n = insert_many(cur, "payments", 
                    ["payment_id", "booking_id", "history_id", "amount_usd", "payment_method", "status"], rows)
    print(f"  payments: {n} rows")


def seed_feedback(cur):
    data = load("feedback.json")
    rows = [
        (f.get("feedback_id"), f.get("user_id"), f.get("rating"), f.get("comment"))
        for f in data
    ]
    n = insert_many(cur, "feedback", 
                    ["feedback_id", "user_id", "rating", "comments"], rows)
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