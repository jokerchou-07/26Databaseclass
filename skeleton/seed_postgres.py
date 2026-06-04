"""
Seed PostgreSQL with all TransitFlow mock data from train-mock-data/.

Usage:
    python skeleton/seed_postgres.py

Run AFTER docker-compose up -d.
You must first design and create your tables in databases/relational/schema.sql.
Safe to re-run: implement your inserts with ON CONFLICT DO NOTHING.
"""

import json
import hashlib
import os
import sys
import bcrypt
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta

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
    
    # 1. 寫入捷運主班次表，動態對應 JSON 裡的真實欄位
    schedule_rows = [
        (s.get("schedule_id"), s.get("line", "M1"), s.get("frequency_min", 5), s.get("base_fare_usd", 0.80)) 
        for s in data
    ]
    n1 = insert_many(cur, "metro_schedules", ["schedule_id", "line", "frequency_min", "fare"], schedule_rows)
    print(f"  metro_schedules: {n1} rows")

    # 2. 【核心修復】解析扁平化的 stops 資料並計算抵達時間
    stop_rows = []
    for schedule in data:
        # 1. Match the exact key from the provided JSON
        stops_list = schedule.get("stops_in_order", [])
        
        # 2. Get the base starting time of the train (e.g., "05:30")
        base_time_str = schedule.get("first_train_time", "06:00")
        base_h, base_m = map(int, base_time_str.split(":"))
        
        for index, station_id in enumerate(stops_list):
            # 3. Fetch the estimated travel time
            travel_times = schedule.get("travel_time_from_origin_min", {})
            travel_time = travel_times.get(station_id, 0)
            
            # 4. Calculate actual valid TIME string (HH:MM:SS) for PostgreSQL
            total_m = base_m + travel_time
            arr_h = (base_h + (total_m // 60)) % 24
            arr_m = total_m % 60
            arrival_time_str = f"{arr_h:02d}:{arr_m:02d}:00"

            stop_rows.append((
                schedule.get("schedule_id"),
                station_id,             
                arrival_time_str,       # 👈 Insert the valid HH:MM:SS string here!
                index + 1               
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
    # 💡 關鍵第一步：動態讀取火車總班次表，抓出「所有實際存在的班次 ID」
    schedules_data = load("national_rail_schedules.json")
    all_schedules = [s.get("schedule_id") for s in schedules_data if s.get("schedule_id")]

    data = load("national_rail_seat_layouts.json")
    rows = []
    
    seeded_schedules = set()   # 記錄在座位檔中已經處理過的班次 ID
    default_template = None    # 用來暫存第一個看到的車廂座位範本

    # 1. 進入你原本的迴圈：處理 JSON 裡面原本就有的配置
    for layout in data:
        schedule_id = layout.get("schedule_id")
        if not schedule_id:
            continue
        
        seeded_schedules.add(schedule_id) # 標記這個班次已經有座位了
        
        # 💡 動態捕捉第一個有資料的車廂配置，當作萬用備份範本
        if not default_template and layout.get("coaches"):
            default_template = layout.get("coaches")
        
        # 先進入第一層：抓取 coaches (車廂)
        for coach_data in layout.get("coaches", []):
            coach = coach_data.get("coach")
            fare_class = coach_data.get("fare_class")
            
            # 再進入第二層：抓取 seats (座位)
            for seat in coach_data.get("seats", []):
                # 注意：JSON 裡的 key 是 seat_id，不是 seat_number
                seat_num = seat.get("seat_id") 
                
                layout_id = f"LAYOUT_{schedule_id}_{coach}_{seat_num}"
                rows.append((
                    layout_id,
                    schedule_id,
                    coach,
                    seat_num,
                    fare_class
                ))
                
    # 2. 🚀 智慧防禦機制：比對總班次表，只要發現漏掉的班次，自動拿範本解開並補齊
    for sch_id in all_schedules:
        if sch_id not in seeded_schedules and default_template:
            # 沿用你原本熟悉的兩層解開邏輯，只是把 schedule_id 換成漏掉的 sch_id
            for coach_data in default_template:
                coach = coach_data.get("coach")
                fare_class = coach_data.get("fare_class")
                
                for seat in coach_data.get("seats", []):
                    seat_num = seat.get("seat_id") 
                    
                    layout_id = f"LAYOUT_{sch_id}_{coach}_{seat_num}"
                    rows.append((
                        layout_id,
                        sch_id,
                        coach,
                        seat_num,
                        fare_class
                    ))
                
    n = insert_many(cur, "national_rail_seat_layouts", 
                    ["layout_id", "schedule_id", "coach_number", "seat_number", "fare_class"], rows)
    print(f"  national_rail_seat_layouts: {n} rows")

def seed_users(cur):
    data = load("registered_users.json")
    rows = []
    for u in data:

        # 1. 抓取完整名字並切開
        user_name = u.get("name") or u.get("full_name") or u.get("first_name") or "Unknown User"
        parts = user_name.split(" ", 1)
        first_name = parts[0]
        surname = parts[1] if len(parts) > 1 else ""
        
        # 2. 處理團隊規定的新欄位 (如果 JSON 裡沒有，就塞預設值給它)
        year_of_birth = u.get("year_of_birth") or 1990
        secret_question = u.get("secret_question") or "What is your favorite color?"
        secret_answer = u.get("secret_answer") or "Blue"
        
        # 3. 密碼加密 (使用報告中承諾的 bcrypt，淘汰 SHA-256)
        original_password = u.get("password", "default_pass")
        hashed_password = bcrypt.hashpw(original_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        # 4. 把所有資料正確裝箱 (注意這裡的數量和順序！)
        rows.append((
            u.get("user_id"), 
            first_name, 
            surname, 
            year_of_birth,     # 補上出生年份
            u.get("email"), 
            hashed_password,   # 使用 bcrypt 雜湊後的密碼
            secret_question,   # 補上安全提示問題
            secret_answer      # 補上安全提示答案
        ))
        
    # 5. 寫入資料庫 (欄位列表必須跟上面 rows.append 的順序一模一樣！)
    n = insert_many(
        cur, 
        "users", 
        ["user_id", "first_name", "surname", "year_of_birth", "email", "password", "secret_question", "secret_answer"], 
        rows
    )
    print(f"   users: {n} rows")

def seed_national_rail_bookings(cur):
    data = load("bookings.json")
    rows = []
    
    for b in data:
        # 1. 狀態清洗：把不合規的 'completed' 強制轉為 'confirmed'
        raw_status = b.get("status", "confirmed").lower()
        if raw_status == "completed":
            final_status = "confirmed"
        elif raw_status not in ['confirmed', 'cancelled', 'refunded']:
            final_status = "confirmed"
        else:
            final_status = raw_status

        # 2. 資料裝箱：盡量抓取 JSON 的真實資料，沒有的話再給預設值
        rows.append((
            b.get("booking_id"), 
            b.get("user_id"), 
            b.get("schedule_id", "NR_SCH01"),            # 優先抓 JSON，沒有才用預設值
            b.get("origin_station_id", "STN_TPE"),       # 補上起點 (Schema 需要)
            b.get("destination_station_id", "STN_ZLI"),  # 補上終點 (Schema 需要)
            b.get("travel_date"), 
            b.get("departure_time", "07:00:00"),         # 資料庫 TIME 型態建議補上秒數格式
            b.get("carriage_number", "A"),               # ⚠️ 檢查你的 JSON 裡是否有座位資訊
            b.get("seat_number", "1A"),                  # 如果 JSON 裡有獨立的 seat_number 就會抓到，才不會大家都坐 1A
            b.get("amount_usd", 0.0), 
            final_status                                 # 放進我們清洗乾淨的狀態
        ))

    # 3. 寫入資料庫：確保欄位數量與上方 rows.append 的順序完全一致
    n = insert_many(
        cur,
        "bookings",
        [
            "booking_id", "user_id", "schedule_id", 
            "origin_station_id", "destination_station_id", 
            "travel_date", "departure_time", "carriage_number", 
            "seat_number", "amount_usd", "status"
        ], 
        rows
    )
    print(f"   bookings: {n} rows")


def seed_metro_travels(cur):
    data = load("metro_travel_history.json") 
    rows = []
    
    for t in data:
        # 1. 抓取進站時間
        entry_time = t.get("entry_time", "2026-05-28 08:00:00")
        
        # 2. 智慧防呆：如果 JSON 裡沒有 travel_date，就從 entry_time 的字串切出日期 (YYYY-MM-DD)
        travel_date = t.get("travel_date")
        if not travel_date and entry_time:
            travel_date = entry_time.split(" ")[0] # 把 "2026-05-28 08:00:00" 切成 "2026-05-28"
            
        # 3. 處理欄位名稱差異 (相容你早期的 JSON key，如 trip_id, amount_usd)
        history_id = t.get("history_id") or t.get("trip_id")
        entry_station = t.get("entry_station_id") or t.get("origin_station_id")
        exit_station = t.get("exit_station_id") or t.get("destination_station_id")
        fare = t.get("fare") or t.get("amount_usd") or 0.0
        
        # 4. 精準裝箱
        rows.append((
            history_id, 
            t.get("user_id"), 
            t.get("schedule_id"), # 這個欄位 schema 允許是 null，所以找不到也沒關係
            entry_station, 
            exit_station, 
            travel_date,          # 💡 補上我們剛剛切出來的日期
            entry_time, 
            t.get("exit_time"), 
            t.get("ticket_type", "Single Ticket"), 
            fare
        ))

    # 5. 寫入資料庫 (確認欄位陣列順序完全對齊 schema.sql)
    n = insert_many(
        cur,
        "metro_travel_history",
        [
            "history_id", "user_id", "schedule_id", 
            "entry_station_id", "exit_station_id", 
            "travel_date", "entry_time", "exit_time", 
            "ticket_type", "fare"
        ],
        rows
    )
    print(f"   metro_travel_history: {n} rows")

def seed_payments(cur):
    data = load("payments.json")
    rows = []
    for p in data:
        # 1. 抓取目標 ID
        raw_target_id = p.get("booking_id") or p.get("trip_id") or p.get("history_id")
        
        # 2. 智慧分流：根據前綴字元決定外鍵，並同時推斷 reference_type
        b_id = None
        h_id = None
        ref_type = "national_rail"  # 預設防呆
        
        if raw_target_id:
            if raw_target_id.startswith("BK") or raw_target_id.startswith("NR"):
                b_id = raw_target_id
                ref_type = "national_rail"
            elif raw_target_id.startswith("MT"):
                h_id = raw_target_id
                ref_type = "metro"

        # 3. 狀態清洗：把 'paid' 強制轉為合法的 'success'
        raw_status = p.get("status") or p.get("payment_status") or "paid"
        raw_status = raw_status.lower()
        if raw_status == "paid":
            final_status = "success"
        elif raw_status not in ["success", "failed", "refunded"]:
            final_status = "success"
        else:
            final_status = raw_status

        amount = p.get("amount_usd") or p.get("amount") or 0.00
        
        # 4. 精準裝箱 (總共 8 個欄位)
        rows.append((
            p.get("payment_id"), 
            p.get("user_id"),  # 💡 補上付錢的人
            b_id,   
            h_id,   
            ref_type,          # 💡 補上 Schema 規定的 NOT NULL 分類
            amount, 
            p.get("payment_method", "credit_card"),      
            final_status       # 💡 放入清洗過後的狀態
        ))
        
    # 5. 寫入資料庫
    n = insert_many(
        cur, 
        "payments", 
        ["payment_id", "user_id", "booking_id", "history_id", "reference_type", "amount_usd", "payment_method", "status"], 
        rows
    )
    print(f"   payments: {n} rows")

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