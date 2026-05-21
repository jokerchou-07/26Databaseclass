-- ============================================================
--  TransitFlow PostgreSQL Schema
-- ============================================================

-- ============================================================
-- 1. 核心基礎資料表 (Core Tables)
-- ============================================================
-- 捷運車站表
CREATE TABLE IF NOT EXISTS metro_stations (
    station_id   VARCHAR(50)  PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    zone         INT          NOT NULL
);

-- 國鐵車站表
CREATE TABLE IF NOT EXISTS national_rail_stations (
    station_id   VARCHAR(50)  PRIMARY KEY,
    name         VARCHAR(100) NOT NULL
);

-- 註冊使用者表
CREATE TABLE IF NOT EXISTS users (
    user_id      VARCHAR(50)  PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    email        VARCHAR(150) UNIQUE NOT NULL,
    password     VARCHAR(255) NOT NULL,
    created_at   TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================================================
-- 2. 班次與座位配置表 (Schedules & Layouts)
-- ============================================================

-- 捷運班次表
CREATE TABLE IF NOT EXISTS metro_schedules (
    schedule_id   VARCHAR(50)  PRIMARY KEY,
    line          VARCHAR(50)  NOT NULL,   -- 例如: M1, M2
    frequency_min INT          NOT NULL,   -- 班距
    fare          NUMERIC(10,2) NOT NULL   -- 基本票價
);

-- 捷運班次停靠站表 (處理時刻表與車站的多對多)
CREATE TABLE IF NOT EXISTS metro_schedule_stops (
    schedule_id   VARCHAR(50)  REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    station_id    VARCHAR(50)  REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    arrival_time  TIME         NOT NULL,
    stop_order    INT          NOT NULL,
    PRIMARY KEY (schedule_id, station_id)
);

-- 國鐵班次表
CREATE TABLE IF NOT EXISTS national_rail_schedules (
    schedule_id            VARCHAR(50)  PRIMARY KEY,
    route_name             VARCHAR(100) NOT NULL, -- 例如: NR1
    service_type           VARCHAR(50)  NOT NULL, -- Express, Normal
    origin_station_id      VARCHAR(50)  REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(50)  REFERENCES national_rail_stations(station_id),
    departure_time         TIME         NOT NULL,
    arrival_time           TIME         NOT NULL,
    fare_standard          NUMERIC(10,2) NOT NULL,
    fare_first             NUMERIC(10,2) NOT NULL
);

-- 國鐵座位配置明細表 (對應 national_rail_seat_layouts.json)
CREATE TABLE IF NOT EXISTS national_rail_seat_layouts (
    layout_id     VARCHAR(50)  PRIMARY KEY, -- 格式通常為 LAYOUT_NR_SCH01_A_1A 之類
    schedule_id   VARCHAR(50)  REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    coach_number  VARCHAR(10)  NOT NULL,    -- Car A, Car B
    seat_number   VARCHAR(10)  NOT NULL,    -- 1A, 1B
    fare_class    VARCHAR(50)  NOT NULL     -- standard, first
);

-- ============================================================
-- 3. 使用者乘車與交易紀錄表 (Activity & Transactions)
-- ============================================================

-- 國鐵訂位紀錄表
CREATE TABLE IF NOT EXISTS bookings (
    booking_id       VARCHAR(50)  PRIMARY KEY,
    user_id          VARCHAR(50)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    schedule_id      VARCHAR(50)  NOT NULL REFERENCES national_rail_schedules(schedule_id),
    travel_date      DATE         NOT NULL,  -- 乘車日期
    departure_time   TIME         NOT NULL,
    carriage_number  VARCHAR(10)  NOT NULL,  -- 改用 VARCHAR 以符合 Car A 等字串
    seat_number      VARCHAR(10)  NOT NULL,
    amount_usd       NUMERIC(10,2) NOT NULL,
    status           VARCHAR(50)  NOT NULL,  -- confirmed, cancelled
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- 捷運搭乘歷史紀錄表
CREATE TABLE IF NOT EXISTS metro_travel_history (
    history_id        VARCHAR(50)  PRIMARY KEY,
    user_id           VARCHAR(50)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    entry_station_id  VARCHAR(50)  NOT NULL REFERENCES metro_stations(station_id),
    exit_station_id   VARCHAR(50)  REFERENCES metro_stations(station_id),
    entry_time        TIMESTAMPTZ  NOT NULL,
    exit_time         TIMESTAMPTZ,
    fare              NUMERIC(10,2) DEFAULT 0.00
);

-- 付款紀錄表
CREATE TABLE IF NOT EXISTS payments (
    payment_id     VARCHAR(50)  PRIMARY KEY,
    booking_id     VARCHAR(50)  REFERENCES bookings(booking_id) ON DELETE SET NULL,
    history_id     VARCHAR(50)  REFERENCES metro_travel_history(history_id) ON DELETE SET NULL,
    amount_usd     NUMERIC(10,2) NOT NULL,
    payment_method VARCHAR(50)  NOT NULL, -- credit_card, easycard
    status         VARCHAR(50)  NOT NULL, -- paid, refunded, failed
    payment_date   TIMESTAMPTZ  DEFAULT NOW()
);

-- 意見回饋表
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id  VARCHAR(50)  PRIMARY KEY,
    user_id      VARCHAR(50)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    rating       INT          NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comments     TEXT,
    submitted_at TIMESTAMPTZ  DEFAULT NOW()
);


-- ============================================================
--  VECTOR SCHEMA  (RAG / Help Desk) — do not modify
-- ============================================================

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  -- 'refund', 'booking', 'conduct'
    content     TEXT         NOT NULL,
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- Fix: 幫 INDEX 加上明確名稱 idx_policy_documents_embedding，修正語法錯誤
CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding 
ON policy_documents 
USING hnsw (embedding vector_cosine_ops);