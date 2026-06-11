-- TASK 6 EXTENSION: Dynamic Disruption Management and Adaptive Routing Engine
-- TASK 6 EXTENSION INDEX: Instant lookup for active network bottlenecks during route-finding
-- New table: station_disruptions
-- New index: idx_disruptions_active_station
-- ==============================================================================
-- TransitFlow Relational Database Schema (PostgreSQL)
-- This file defines the DDL structure for users, stations, schedules, seat layouts,
-- bookings, travel history, payments, feedback, and real-time network disruptions.
-- ==============================================================================

-- Enable pgvector extension for RAG policy searching
CREATE EXTENSION IF NOT EXISTS vector;

-- Drop tables in reverse dependency order to avoid constraint violations during resets
DROP TABLE IF EXISTS station_disruptions CASCADE;
DROP TABLE IF EXISTS feedback CASCADE;
DROP TABLE IF EXISTS payments CASCADE;
DROP TABLE IF EXISTS metro_travel_history CASCADE;
DROP TABLE IF EXISTS bookings CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS national_rail_seat_layouts CASCADE;
DROP TABLE IF EXISTS national_rail_schedule_stops CASCADE;
DROP TABLE IF EXISTS national_rail_schedules CASCADE;
DROP TABLE IF EXISTS metro_schedule_stops CASCADE;
DROP TABLE IF EXISTS metro_schedules CASCADE;
DROP TABLE IF EXISTS national_rail_stations CASCADE;
DROP TABLE IF EXISTS metro_stations CASCADE;
DROP TABLE IF EXISTS policy_documents CASCADE;

-- ============================================================
-- 1. Core Tables
-- ============================================================

-- metro_stations
CREATE TABLE IF NOT EXISTS metro_stations (
    -- PK Decision: Chosen VARCHAR(50) over SERIAL/UUID to align perfectly with the external 
    -- transportation JSON data source IDs and maintain exact node identity matching in Neo4j.
    station_id   VARCHAR(50)  PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    zone         INT          NOT NULL,
    is_interchange BOOLEAN    DEFAULT FALSE
);

-- national_rail_stations
CREATE TABLE IF NOT EXISTS national_rail_stations (
    -- PK Decision: Chosen VARCHAR(50) over SERIAL to ensure seamless cross-referencing with 
    -- standard National Rail station codes and facilitate direct mapping to Graph DB nodes.
    station_id   VARCHAR(50)  PRIMARY KEY,
    name         VARCHAR(100) NOT NULL,
    is_interchange BOOLEAN    DEFAULT FALSE
);

-- users
CREATE TABLE IF NOT EXISTS users (
    -- PK Decision: Chosen VARCHAR(50) over SERIAL to support secure, system-generated hash 
    -- identifiers or custom UUID strings from the application layer.
    user_id         VARCHAR(50)  PRIMARY KEY,
    first_name      VARCHAR(50)  NOT NULL,
    surname         VARCHAR(50)  NOT NULL,
    year_of_birth   INT          NOT NULL,
    email           VARCHAR(150) UNIQUE NOT NULL,
    -- Security Note: MUST store Argon2id or bcrypt hashed string, NEVER plain-text.
    password        VARCHAR(255) NOT NULL,
    role            VARCHAR(20)  DEFAULT 'passenger',
    secret_question VARCHAR(255),
    secret_answer   VARCHAR(255),
    created_at      TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================================================
-- 2. Schedules & Layouts
-- ============================================================

-- metro_schedules
CREATE TABLE IF NOT EXISTS metro_schedules (
    -- PK Decision: Chosen VARCHAR(50) to use deterministic service strings (e.g., 'SCH_M1').
    schedule_id   VARCHAR(50)  PRIMARY KEY,
    line          VARCHAR(50)  NOT NULL,   
    frequency_min INT          NOT NULL,  
    fare          NUMERIC(10,2) NOT NULL,
    operating_days VARCHAR(50)  NOT NULL DEFAULT 'Daily'
);

-- metro_schedule_stops (Junction Table. Resolves the many-to-many relationship between metro schedules and stations by computing dynamic chronological attributes.)
CREATE TABLE IF NOT EXISTS metro_schedule_stops (
    -- Normalisation Note: Junction table created to satisfy 3NF, avoiding array columns.
    schedule_id   VARCHAR(50)  REFERENCES metro_schedules(schedule_id) ON DELETE CASCADE,
    station_id    VARCHAR(50)  REFERENCES metro_stations(station_id) ON DELETE CASCADE,
    arrival_time  TIME         NOT NULL,
    stop_order    INT          NOT NULL,
    PRIMARY KEY (schedule_id, station_id)
);

-- national_rail_schedules
CREATE TABLE IF NOT EXISTS national_rail_schedules (
    -- PK Decision: Chosen VARCHAR(50) to match external train service codes.
    schedule_id            VARCHAR(50)  PRIMARY KEY,
    route_name             VARCHAR(100) NOT NULL,
    service_type           VARCHAR(50)  NOT NULL,
    origin_station_id      VARCHAR(50)  REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    destination_station_id VARCHAR(50)  REFERENCES national_rail_stations(station_id) ON DELETE RESTRICT,
    departure_time         TIME         NOT NULL,
    arrival_time           TIME         NOT NULL,
    duration_min           INT          NOT NULL DEFAULT 0,
    fare_standard          NUMERIC(10,2) NOT NULL,
    fare_first             NUMERIC(10,2) NOT NULL,
    operating_days         VARCHAR(50)  NOT NULL DEFAULT 'Daily'
);

-- national_rail_schedule_stops
CREATE TABLE IF NOT EXISTS national_rail_schedule_stops (
    schedule_id  VARCHAR(50) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    station_id   VARCHAR(50) REFERENCES national_rail_stations(station_id) ON DELETE CASCADE,
    stop_order   INT NOT NULL,
    arrival_time TIME NOT NULL,
    PRIMARY KEY (schedule_id, station_id)
);

-- national_rail_seat_layouts
CREATE TABLE IF NOT EXISTS national_rail_seat_layouts (
    -- PK Decision: Chosen VARCHAR(50) to support composite logical IDs (e.g., LAYOUT_NR_SCH01_A_1A).
    layout_id     VARCHAR(50)  PRIMARY KEY, 
    schedule_id   VARCHAR(50)  REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    coach_number  VARCHAR(10)  NOT NULL,    
    seat_number   VARCHAR(10)  NOT NULL,    
    fare_class    VARCHAR(50)  NOT NULL CHECK (fare_class IN ('standard', 'first')),
    is_booked     BOOLEAN      DEFAULT FALSE,
    UNIQUE (schedule_id, coach_number, seat_number)
);

-- ============================================================
-- 3. Activity & Transactions
-- ============================================================

-- bookings
CREATE TABLE IF NOT EXISTS bookings (
    -- PK Decision: Chosen VARCHAR(50) to allow application-side generation of tracking IDs.
    -- Delete Strategy Note: Using soft delete ('cancelled' status) to preserve audit trails.
    -- Soft delete: bookings use status column ('cancelled') to preserve audit history.
    -- Hard cascade: child records (stops, layouts, payments) cascade with parent deletion because they have no independent meaning without their parent record.
    -- RESTRICT: schedule FKs on bookings use RESTRICT to prevent accidental data loss when active bookings exist against a schedule.
    booking_id       VARCHAR(50)  PRIMARY KEY,
    user_id          VARCHAR(50)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    schedule_id      VARCHAR(50)  NOT NULL REFERENCES national_rail_schedules(schedule_id) ON DELETE RESTRICT,
    origin_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    travel_date      DATE         NOT NULL,  
    departure_time   TIME         NOT NULL,
    carriage_number  VARCHAR(10)  NOT NULL,  
    seat_number      VARCHAR(10)  NOT NULL,
    amount_usd       NUMERIC(10,2) NOT NULL,
    status           VARCHAR(50)  NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'refunded')),  
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);

-- metro_travel_history
CREATE TABLE IF NOT EXISTS metro_travel_history (
    -- PK Decision: Chosen VARCHAR(50) for consistency across all transaction records.
    history_id        VARCHAR(50)  PRIMARY KEY,
    user_id           VARCHAR(50)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    schedule_id       VARCHAR(50)  REFERENCES metro_schedules(schedule_id),
    entry_station_id  VARCHAR(50)  NOT NULL REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    exit_station_id   VARCHAR(50)  REFERENCES metro_stations(station_id) ON DELETE RESTRICT,
    travel_date       DATE         NOT NULL,
    entry_time        TIMESTAMPTZ  NOT NULL,
    exit_time         TIMESTAMPTZ,
    ticket_type       VARCHAR(50)  NOT NULL DEFAULT 'Single Ticket',
    fare              NUMERIC(10,2) DEFAULT 0.00
);

-- payments
CREATE TABLE IF NOT EXISTS payments (
    -- PK Decision: Chosen VARCHAR(50) for integration with external payment gateway IDs.
    payment_id     VARCHAR(50)  PRIMARY KEY,
    user_id        VARCHAR(50)  REFERENCES users(user_id) ON DELETE CASCADE,
    booking_id     VARCHAR(50)  REFERENCES bookings(booking_id) ON DELETE SET NULL,
    history_id     VARCHAR(50)  REFERENCES metro_travel_history(history_id) ON DELETE SET NULL,
    reference_type VARCHAR(20)  NOT NULL CHECK (reference_type IN ('national_rail', 'metro')),
    amount_usd     NUMERIC(10,2) NOT NULL,
    payment_method VARCHAR(50)  NOT NULL, 
    status         VARCHAR(50)  NOT NULL DEFAULT 'success' CHECK (status IN ('success', 'failed', 'refunded')), 
    payment_date   TIMESTAMPTZ  DEFAULT CURRENT_TIMESTAMP
);

-- feedback
CREATE TABLE IF NOT EXISTS feedback (
    -- PK Decision: Chosen VARCHAR(50) for uniform ID structures across the database.
    feedback_id  VARCHAR(50)  PRIMARY KEY,
    user_id      VARCHAR(50)  NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    booking_id   VARCHAR(50)  REFERENCES bookings(booking_id) ON DELETE SET NULL,
    rating       INT          NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comments     TEXT,
    submitted_at TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================================================
-- 4. VECTOR SCHEMA (RAG / Help Desk)
-- ============================================================

CREATE TABLE IF NOT EXISTS policy_documents (
    id          SERIAL       PRIMARY KEY,
    title       VARCHAR(200) NOT NULL,
    category    VARCHAR(50)  NOT NULL,  
    content     TEXT         NOT NULL,
    embedding   vector(768),
    source_file VARCHAR(200),
    created_at  TIMESTAMPTZ  DEFAULT NOW()
);

-- ============================================================
-- 5. TASK 6 EXTENSION: DYNAMIC DISRUPTION TABLES & INDEXES
-- ============================================================

CREATE TABLE station_disruptions (
    disruption_id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL, 
    network_type VARCHAR(20) NOT NULL CHECK (network_type IN ('metro', 'national_rail')),
    severity VARCHAR(20) DEFAULT 'DELAY' CHECK (severity IN ('DELAY', 'CLOSED')),
    description TEXT NOT NULL,
    reported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- Index for RAG cosine distance query speedups
CREATE INDEX IF NOT EXISTS idx_policy_documents_embedding 
ON policy_documents USING hnsw (embedding vector_cosine_ops);

-- Foreign Key Optimization Indexes for transactional joins
CREATE INDEX IF NOT EXISTS idx_bookings_user ON bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_bookings_schedule ON bookings(schedule_id);
CREATE INDEX IF NOT EXISTS idx_payments_lookup ON payments(reference_type, booking_id, history_id);

-- TASK 6 EXTENSION INDEX: Instant lookup for active network bottlenecks during route-finding
CREATE INDEX IF NOT EXISTS idx_disruptions_active_station 
ON station_disruptions(station_id) 
WHERE resolved_at IS NULL;
