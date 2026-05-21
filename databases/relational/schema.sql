-- ============================================================
--  TransitFlow PostgreSQL Schema
-- ============================================================

-- ============================================================
-- 1. 核心基礎資料表 (Core Tables)
-- ============================================================

-- 捷運車站表 (metro_stations.json)
CREATE TABLE IF NOT EXISTS metro_stations (
    station_id   VARCHAR(50)  PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    zone         INT          NOT NULL
);

-- 國鐵車站表 (national_rail_stations.json)
CREATE TABLE IF NOT EXISTS national_rail_stations (
    station_id   VARCHAR(50)  PRIMARY KEY,
    name         VARCHAR(100) NOT NULL
);

-- 註冊使用者表 (registered_users.json)
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

-- 捷運班次表 (metro_schedules.json)
CREATE TABLE IF NOT EXISTS metro_schedules (
    schedule_id        VARCHAR(50)  PRIMARY KEY,
    line               VARCHAR(50)  NOT NULL,   -- 例如: "Red", "Blue"
    arrival_time       TIME         NOT NULL,   -- 僅記錄時間點
    departure_time     TIME         NOT NULL,
    station_id         VARCHAR(50)  NOT NULL,
    FOREIGN KEY (station_id) REFERENCES metro_stations(station_id) ON DELETE CASCADE
);

-- 國鐵車次與座位配置表 (national_rail_seat_layouts.json)
-- 先建立配置表，因為車次表需要關聯它
CREATE TABLE IF NOT EXISTS national_rail_seat_layouts (
    layout_id          VARCHAR(50)  PRIMARY KEY,
    train_type         VARCHAR(50)  NOT NULL,   -- 例如: "Express", "Local"
    total_carriages    INT          NOT NULL,
    seats_per_carriage INT          NOT NULL
);

-- 國鐵班次表 (national_rail_schedules.json)
CREATE TABLE IF NOT EXISTS national_rail_schedules (
    schedule_id        VARCHAR(50)  PRIMARY KEY,
    train_number       VARCHAR(50)  NOT NULL,   -- 車次號碼
    departure_time     TIMESTAMPTZ  NOT NULL,   -- 國鐵通常包含日期與時間
    arrival_time       TIMESTAMPTZ  NOT NULL,
    from_station_id    VARCHAR(50)  NOT NULL,
    to_station_id      VARCHAR(50)  NOT NULL,
    layout_id          VARCHAR(50)  NOT NULL,
    FOREIGN KEY (from_station_id) REFERENCES national_rail_stations(station_id),
    FOREIGN KEY (to_station_id) REFERENCES national_rail_stations(station_id),
    FOREIGN KEY (layout_id) REFERENCES national_rail_seat_layouts(layout_id)
);

-- ============================================================
-- 3. 使用者乘車與交易紀錄表 (Activity & Transactions)
-- ============================================================

-- 國鐵訂位紀錄表 (bookings.json)
CREATE TABLE IF NOT EXISTS bookings (
    booking_id         VARCHAR(50)  PRIMARY KEY,
    user_id            VARCHAR(50)  NOT NULL,
    schedule_id        VARCHAR(50)  NOT NULL,
    carriage_number    INT          NOT NULL,
    seat_number        VARCHAR(10)  NOT NULL,
    status             VARCHAR(20)  NOT NULL,   -- 'confirmed', 'cancelled'
    booking_date       TIMESTAMPTZ  DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (schedule_id) REFERENCES national_rail_schedules(schedule_id)
);

-- 捷運搭乘歷史紀錄表 (metro_travel_history.json)
CREATE TABLE IF NOT EXISTS metro_travel_history (
    history_id         VARCHAR(50)  PRIMARY KEY,
    user_id            VARCHAR(50)  NOT NULL,
    entry_station_id   VARCHAR(50)  NOT NULL,
    exit_station_id    VARCHAR(50),             -- 考慮到可能剛進站尚未出站，允許 NULL
    entry_time         TIMESTAMPTZ  NOT NULL,
    exit_time          TIMESTAMPTZ,
    fare               NUMERIC(10, 2) DEFAULT 0.00,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (entry_station_id) REFERENCES metro_stations(station_id),
    FOREIGN KEY (exit_station_id) REFERENCES metro_stations(station_id)
);

-- 付款紀錄表 (payments.json)
CREATE TABLE IF NOT EXISTS payments (
    payment_id         VARCHAR(50)  PRIMARY KEY,
    booking_id         VARCHAR(50),             -- 如果是付國鐵票
    history_id         VARCHAR(50),             -- 如果是付捷運扣款 (依 mock data 設計調整)
    amount             NUMERIC(10, 2) NOT NULL,
    payment_method     VARCHAR(50)  NOT NULL,   -- 'credit_card', 'easycard', etc.
    status             VARCHAR(20)  NOT NULL,   -- 'paid', 'refunded', 'failed'
    payment_date       TIMESTAMPTZ  DEFAULT NOW(),
    FOREIGN KEY (booking_id) REFERENCES bookings(booking_id) ON DELETE SET NULL,
    FOREIGN KEY (history_id) REFERENCES metro_travel_history(history_id) ON DELETE SET NULL
);

-- 意見回饋表 (feedback.json)
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id        VARCHAR(50)  PRIMARY KEY,
    user_id            VARCHAR(50)  NOT NULL,
    rating             INT          NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comments           TEXT,
    submitted_at       TIMESTAMPTZ  DEFAULT NOW(),
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
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