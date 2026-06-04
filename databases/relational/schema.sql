-- TASK 6 EXTENSION: Live Disruption Management and Adaptive Routing Engine
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
DROP TABLE IF EXISTS national_rail_bookings CASCADE;
DROP TABLE IF EXISTS registered_users CASCADE;
DROP TABLE IF EXISTS national_rail_seat_layouts CASCADE;
DROP TABLE IF EXISTS national_rail_schedules CASCADE;
DROP TABLE IF EXISTS metro_schedules CASCADE;
DROP TABLE IF EXISTS national_rail_stations CASCADE;
DROP TABLE IF EXISTS metro_stations CASCADE;
DROP TABLE IF EXISTS policy_documents CASCADE;

-- ── 1. CORE STATION & POLICY TABLES ──────────────────────────────────────────

CREATE TABLE metro_stations (
    station_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    zone INT NOT NULL,
    is_interchange BOOLEAN DEFAULT FALSE
);

CREATE TABLE national_rail_stations (
    station_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    is_interchange BOOLEAN DEFAULT FALSE
);

CREATE TABLE policy_documents (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(768) -- Matches nomic-embed-text dimensions from Ollama
);

-- ── 2. TRANSIT TIMETABLES & SCHEDULES ────────────────────────────────────────

CREATE TABLE metro_schedules (
    schedule_id VARCHAR(50) NOT NULL,
    line VARCHAR(20) NOT NULL,
    origin_station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    departure_time_string VARCHAR(20) NOT NULL, -- Stored as string from mock data format
    fare_standard NUMERIC(10, 2) NOT NULL,
    operating_days VARCHAR(50) NOT NULL,
    PRIMARY KEY (schedule_id)
);

CREATE TABLE national_rail_schedules (
    schedule_id VARCHAR(50) NOT NULL,
    service_type VARCHAR(50) NOT NULL, -- e.g., Express, Normal
    origin_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    departure_time_string VARCHAR(20) NOT NULL,
    duration_min INT NOT NULL,
    fare_standard NUMERIC(10, 2) NOT NULL,
    fare_first NUMERIC(10, 2) NOT NULL,
    operating_days VARCHAR(50) NOT NULL,
    PRIMARY KEY (schedule_id)
);

CREATE TABLE national_rail_seat_layouts (
    layout_id SERIAL PRIMARY KEY,
    schedule_id VARCHAR(50) REFERENCES national_rail_schedules(schedule_id) ON DELETE CASCADE,
    coach VARCHAR(5) NOT NULL, -- e.g., 'A', 'B'
    seat_number VARCHAR(5) NOT NULL, -- e.g., '1A', '1B'
    class VARCHAR(20) NOT NULL CHECK (class IN ('standard', 'first')),
    is_booked BOOLEAN DEFAULT FALSE,
    UNIQUE (schedule_id, coach, seat_number)
);

-- ── 3. USER MANAGEMENT & TRANSACTIONAL TABLES ────────────────────────────────

CREATE TABLE registered_users (
    user_id VARCHAR(50) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'passenger'
);

CREATE TABLE national_rail_bookings (
    booking_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) REFERENCES registered_users(user_id) ON DELETE CASCADE,
    schedule_id VARCHAR(50) REFERENCES national_rail_schedules(schedule_id),
    origin_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES national_rail_stations(station_id),
    travel_date DATE NOT NULL,
    departure_time_string VARCHAR(20) NOT NULL,
    coach VARCHAR(5) NOT NULL,
    seat_number VARCHAR(5) NOT NULL,
    fare_class VARCHAR(20) NOT NULL CHECK (fare_class IN ('standard', 'first')),
    amount_usd NUMERIC(10, 2) NOT NULL,
    status VARCHAR(20) DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'refunded'))
);

CREATE TABLE metro_travel_history (
    trip_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) REFERENCES registered_users(user_id) ON DELETE CASCADE,
    schedule_id VARCHAR(50) REFERENCES metro_schedules(schedule_id),
    origin_station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    destination_station_id VARCHAR(50) REFERENCES metro_stations(station_id),
    travel_date DATE NOT NULL,
    ticket_type VARCHAR(50) NOT NULL, -- e.g., Single Ticket, Day Pass
    amount_usd NUMERIC(10, 2) NOT NULL
);

CREATE TABLE payments (
    payment_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) REFERENCES registered_users(user_id) ON DELETE CASCADE,
    reference_type VARCHAR(20) NOT NULL CHECK (reference_type IN ('national_rail', 'metro')),
    reference_id VARCHAR(50) NOT NULL, -- Maps to booking_id or trip_id
    amount_usd NUMERIC(10, 2) NOT NULL,
    payment_method VARCHAR(50) NOT NULL, -- e.g., Credit Card, Digital Wallet
    payment_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status VARCHAR(20) DEFAULT 'success' CHECK (status IN ('success', 'failed', 'refunded'))
);

CREATE TABLE feedback (
    feedback_id VARCHAR(50) PRIMARY KEY,
    user_id VARCHAR(50) REFERENCES registered_users(user_id) ON DELETE SET NULL,
    booking_id VARCHAR(50) REFERENCES national_rail_bookings(booking_id) ON DELETE SET NULL,
    rating INT NOT NULL CHECK (rating >= 1 AND rating <= 5),
    comment TEXT,
    submitted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ── 4. TASK 6 EXTENSION: DYNAMIC DISRUPTION TABLES ──────────────────────────

CREATE TABLE station_disruptions (
    disruption_id SERIAL PRIMARY KEY,
    station_id VARCHAR(50) NOT NULL, -- Can map to either metro or national rail station IDs
    network_type VARCHAR(20) NOT NULL CHECK (network_type IN ('metro', 'national_rail')),
    severity VARCHAR(20) DEFAULT 'DELAY' CHECK (severity IN ('DELAY', 'CLOSED')),
    description TEXT NOT NULL,
    reported_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP WITH TIME ZONE
);

-- ── 5. PERFORMANCE OPTIMIZATION INDEXES ──────────────────────────────────────

-- Index for RAG cosine distance query speedups
CREATE INDEX IF NOT EXISTS idx_policy_embedding ON policy_documents USING hnsw (embedding vector_cosine_ops);

-- Foreign Key Optimization Indexes for transactional joins
CREATE INDEX IF NOT EXISTS idx_nr_bookings_user ON national_rail_bookings(user_id);
CREATE INDEX IF NOT EXISTS idx_nr_bookings_schedule ON national_rail_bookings(schedule_id);
CREATE INDEX IF NOT EXISTS idx_payments_lookup ON payments(reference_type, reference_id);

-- TASK 6 EXTENSION INDEX: Instant lookup for active network bottlenecks during route-finding
CREATE INDEX IF NOT EXISTS idx_disruptions_active_station 
ON station_disruptions(station_id) 
WHERE resolved_at IS NULL;
