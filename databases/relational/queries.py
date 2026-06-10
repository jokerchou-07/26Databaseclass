"""
TransitFlow — PostgreSQL / Relational Database Layer
=====================================================
This module handles all queries to PostgreSQL.
"""

from __future__ import annotations

import json
import random
import string
import os
import re
import bcrypt
from datetime import datetime, timezone, date
from typing import Optional

import psycopg2
import psycopg2.extras

from skeleton.config import PG_DSN, VECTOR_TOP_K, VECTOR_SIMILARITY_THRESHOLD


def _connect():
    """Return a new psycopg2 connection with autocommit disabled for transaction safety."""
    conn = psycopg2.connect(PG_DSN)
    conn.autocommit = False
    return conn

def _gen_booking_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"BK-{suffix}"

def _gen_payment_id() -> str:
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"PM-{suffix}"

def example_query() -> dict:
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT current_database() AS db;")
            return dict(cur.fetchone())

# ── NATIONAL RAIL AVAILABILITY ────────────────────────────────────────────────
def query_national_rail_availability(
    origin_id: str,
    destination_id: str,
    travel_date: Optional[str] = None,
    **kwargs  # Absorb unexpected LLM arguments like 'network'
) -> list[dict]:
    sql = """
        SELECT 
            s.schedule_id, s.route_name, s.service_type,
            s.departure_time, s.arrival_time,
            o.arrival_time AS origin_time,
            d.arrival_time AS dest_time,
            (d.stop_order - o.stop_order) AS stops_travelled,
            (SELECT COUNT(*) FROM national_rail_seat_layouts l 
             WHERE l.schedule_id = s.schedule_id) AS total_seats
            {booked_subquery}
        FROM national_rail_schedules s
        JOIN national_rail_schedule_stops o 
            ON s.schedule_id = o.schedule_id AND o.station_id = %s
        JOIN national_rail_schedule_stops d 
            ON s.schedule_id = d.schedule_id AND d.station_id = %s
        WHERE o.stop_order < d.stop_order
        ORDER BY o.arrival_time
    """
    if travel_date:
        booked_subquery = """,
            (SELECT COUNT(*) FROM bookings b 
             WHERE b.schedule_id = s.schedule_id 
               AND b.travel_date = %s 
               AND b.status = 'confirmed') AS booked_seats
        """
        params = (travel_date, origin_id, destination_id)
    else:
        booked_subquery = ""
        params = (origin_id, destination_id)

    sql = sql.format(booked_subquery=booked_subquery)

    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            output = []
            for row in cur.fetchall():
                r = dict(row)
                booked = r.get('booked_seats', 0)
                r['available_seats'] = r['total_seats'] - booked
                output.append(r)
            return output


def query_national_rail_fare(
    schedule_id: str,
    fare_class: str,
    stops_travelled: int,
) -> Optional[dict]:
    sql = "SELECT fare_standard, fare_first FROM national_rail_schedules WHERE schedule_id = %s"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()
            if not row:
                return None

            if fare_class == 'first':
                base_fare = float(row['fare_first'])
                per_stop_rate = 2.50
            else:
                base_fare = float(row['fare_standard'])
                per_stop_rate = 1.50

            return {
                "fare_class": fare_class,
                "base_fare_usd": base_fare,
                "per_stop_rate_usd": per_stop_rate,
                "total_fare_usd": base_fare + (per_stop_rate * stops_travelled)
            }

# ── METRO SCHEDULES & FARE ────────────────────────────────────────────────────

def query_metro_schedules(origin_id: str, destination_id: str) -> list[dict]:
    """
    Joins the stop sequence table twice to ensure the train travels 
    from origin to destination in the correct direction (stop_order comparison).

    Args:
        origin_id: The ID of the departure metro station.
        destination_id: The ID of the arrival metro station.

    Returns:
        A list of dictionaries containing schedule ID, line, frequency, fare, and stops travelled.
    """
    sql = """
        SELECT 
            m.schedule_id, m.line, m.frequency_min, m.fare,
            o.arrival_time AS origin_arrival_time,
            d.arrival_time AS dest_arrival_time,
            (d.stop_order - o.stop_order) AS stops_travelled
        FROM metro_schedules m
        JOIN metro_schedule_stops o ON m.schedule_id = o.schedule_id
        JOIN metro_schedule_stops d ON m.schedule_id = d.schedule_id
        WHERE o.station_id = %s AND d.station_id = %s 
          AND o.stop_order < d.stop_order
        ORDER BY o.arrival_time;
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (origin_id, destination_id))
            return [dict(r) for r in cur.fetchall()]


def query_metro_fare(schedule_id: str, stops_travelled: int) -> Optional[dict]:
    """
    Calculates metro fare: base fare + fixed rate per stop travelled.

    Args:
        schedule_id: The ID of the metro schedule.
        stops_travelled: The number of stops between origin and destination.

    Returns:
        A dictionary containing fare details, or None if the schedule is not found.
    """
    sql = "SELECT fare FROM metro_schedules WHERE schedule_id = %s"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id,))
            row = cur.fetchone()
            if not row: 
                return None
            
            base_fare = float(row['fare'])
            per_stop = 0.50
            return {
                "base_fare_usd": base_fare,
                "per_stop_rate_usd": per_stop,
                "total_fare_usd": base_fare + (stops_travelled * per_stop)
            }


# ── SEAT SELECTION ────────────────────────────────────────────────────────────

def query_available_seats(
    schedule_id: str,
    travel_date: str,
    fare_class: str,
) -> list[dict]:
    """
    Finds seats in the layout that do not have a confirmed booking for the specified date.

    Args:
        schedule_id: The ID of the national rail schedule.
        travel_date: The date of travel.
        fare_class: The class of the fare ('standard' or 'first').

    Returns:
        A list of dictionaries representing available seats (seat_id, coach, row, column).
    """
    sql = """
        SELECT coach_number, seat_number 
        FROM national_rail_seat_layouts l
        WHERE schedule_id = %s AND fare_class = %s
          AND NOT EXISTS (
              SELECT 1 FROM bookings b 
              WHERE b.schedule_id = l.schedule_id 
                AND b.carriage_number = l.coach_number 
                AND b.seat_number = l.seat_number 
                AND b.travel_date = %s 
                AND b.status = 'confirmed'
          )
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (schedule_id, fare_class, travel_date))
            
            seats = []
            for r in cur.fetchall():
                match = re.match(r"(\d+)([A-Z]+)", r['seat_number'])
                seats.append({
                    "seat_id": r['seat_number'], 
                    "coach": r['coach_number'],
                    "row": int(match.group(1)) if match else 0, 
                    "column": match.group(2) if match else ""
                })
            return seats


def auto_select_adjacent_seats(available_seats: list[dict], count: int) -> list[str]:
    # Scaffold provided by TAs - Left unmodified
    if not available_seats or count <= 0:
        return []
    if count >= len(available_seats):
        return [s["seat_id"] for s in available_seats[:count]]

    from collections import defaultdict
    rows: dict[int, list[dict]] = defaultdict(list)
    for seat in available_seats:
        rows[seat["row"]].append(seat)

    for row_seats in sorted(rows.values(), key=lambda s: s[0]["row"]):
        if len(row_seats) >= count:
            return [s["seat_id"] for s in row_seats[:count]]

    sorted_seats = sorted(available_seats, key=lambda s: (s["row"], s["column"]))
    return [s["seat_id"] for s in sorted_seats[:count]]


# ── USER & BOOKING QUERIES ────────────────────────────────────────────────────

def query_user_profile(user_email: str) -> Optional[dict]:
    """
    Retrieves a user's profile information by their email.

    Args:
        user_email: The email address of the user.

    Returns:
        A dictionary containing user details, or None if the user is not found.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (user_email,))
            row = cur.fetchone()
            
            if not row:
                return None
                
            user_dict = dict(row)
            
            # Construct full_name for agent compatibility
            first = user_dict.get('first_name', '')
            last = user_dict.get('surname', '')
            user_dict['full_name'] = f"{first} {last}".strip()
            user_dict['name'] = user_dict['full_name']
            
            # Sanitize: never expose password hash to LLM agent layers
            user_dict.pop('password', None)
                
            return user_dict


def query_user_bookings(user_email: str) -> dict:
    """
    Retrieves all booking and travel history for a specific user.

    Args:
        user_email: The email address of the user.

    Returns:
        A dictionary with keys 'national_rail' and 'metro' always present.
    """
    user = query_user_profile(user_email)
    if not user: 
        return {"national_rail": [], "metro": []}
    
    uid = user['user_id']
    history = {"national_rail": [], "metro": []}
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM bookings WHERE user_id = %s ORDER BY travel_date DESC", (uid,))
            history["national_rail"] = [dict(r) for r in cur.fetchall()]
            
            cur.execute("SELECT * FROM metro_travel_history WHERE user_id = %s ORDER BY entry_time DESC", (uid,))
            history["metro"] = [dict(r) for r in cur.fetchall()]
    return history


def query_payment_info(booking_id: str) -> Optional[dict]:
    """
    Retrieves payment information for a specific booking.

    Args:
        booking_id: The ID of the booking.

    Returns:
        A dictionary containing payment details, or None if not found.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM payments WHERE booking_id = %s", (booking_id,))
            row = cur.fetchone()
            return dict(row) if row else None


# ── TRANSACTIONAL OPERATIONS ──────────────────────────────────────────────────

def execute_booking(
    user_id: str,
    schedule_id: str,
    origin_station_id: str,
    destination_station_id: str,
    travel_date: str,
    fare_class: str,
    seat_id: str,
    ticket_type: str = "single",
) -> tuple[bool, dict | str]:
    """
    Executes a booking atomically: both the booking record and payment record
    are inserted in a single transaction. Either both succeed or neither does.

    Args:
        user_id: The ID of the user making the booking.
        schedule_id: The ID of the selected train schedule.
        origin_station_id: The ID of the departure station.
        destination_station_id: The ID of the arrival station.
        travel_date: The date of travel.
        fare_class: The class of the fare ('standard' or 'first').
        seat_id: The specific seat ID, or 'any' for auto-assignment.
        ticket_type: The type of ticket (default is 'single').

    Returns:
        (True, booking_dict) on success, or (False, error_message) on failure.
    """
    # Stop order difference gives actual stops travelled, avoiding hardcoded values
    # that would cause fare miscalculation when origin/destination vary.
    # FIX: Calculate stops_travelled from DB so fare is correct, not hardcoded 0
    with _connect() as conn:
        try:
            conn.autocommit = False
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

                # Look up stop orders to calculate actual stops travelled
                cur.execute("""
                    SELECT o.stop_order AS origin_order, d.stop_order AS dest_order
                    FROM national_rail_schedule_stops o
                    JOIN national_rail_schedule_stops d
                        ON o.schedule_id = d.schedule_id
                    WHERE o.schedule_id = %s
                      AND o.station_id = %s
                      AND d.station_id = %s
                """, (schedule_id, origin_station_id, destination_station_id))
                stop_row = cur.fetchone()
                stops_travelled = 0
                if stop_row:
                    stops_travelled = stop_row['dest_order'] - stop_row['origin_order']

                fare_info = query_national_rail_fare(schedule_id, fare_class, stops_travelled)
                if not fare_info:
                    conn.rollback()
                    return False, "Schedule fare not found."
                amount = fare_info["total_fare_usd"]

                b_id = _gen_booking_id()
                p_id = _gen_payment_id()

                # Handle auto-seat assignment
                if seat_id.lower() == "any":
                    avail_seats = query_available_seats(schedule_id, travel_date, fare_class)
                    if not avail_seats:
                        conn.rollback()
                        return False, "No seats available for this class."
                    seat_id = auto_select_adjacent_seats(avail_seats, 1)[0]
                    coach = next(s["coach"] for s in avail_seats if s["seat_id"] == seat_id)
                else:
                    # Validate seat and get its coach
                    cur.execute(
                        "SELECT coach_number FROM national_rail_seat_layouts "
                        "WHERE schedule_id = %s AND seat_number = %s",
                        (schedule_id, seat_id)
                    )
                    coach_row = cur.fetchone()
                    if not coach_row:
                        conn.rollback()
                        return False, "Invalid seat_id for this schedule."
                    coach = coach_row['coach_number']

                    # Check the seat is not already booked for this date
                    cur.execute("""
                        SELECT 1 FROM bookings
                        WHERE schedule_id = %s
                          AND carriage_number = %s
                          AND seat_number = %s
                          AND travel_date = %s
                          AND status = 'confirmed'
                    """, (schedule_id, coach, seat_id, travel_date))
                    if cur.fetchone():
                        conn.rollback()
                        return False, "Seat is already booked for this date."

                # Step 1: Insert booking record
                cur.execute("""
                    INSERT INTO bookings (
                        booking_id, user_id, schedule_id,
                        origin_station_id, destination_station_id,
                        travel_date, departure_time,
                        carriage_number, seat_number,
                        amount_usd, status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIME, %s, %s, %s, 'confirmed')
                """, (
                    b_id, user_id, schedule_id,
                    origin_station_id, destination_station_id,
                    travel_date, coach, seat_id, amount
                ))

                # Step 2: Insert payment record in the same transaction
                cur.execute("""
                    INSERT INTO payments (
                        payment_id, reference_type, booking_id,
                        amount_usd, payment_method, status
                    )
                    VALUES (%s, 'national_rail', %s, %s, 'credit_card', 'success')
                """, (p_id, b_id, amount))

            # Both inserts succeed — commit once
            conn.commit()
            return True, {
                "booking_id": b_id,
                "user_id": user_id,
                "schedule_id": schedule_id,
                "seat_id": seat_id,
                "coach": coach,
                "amount": amount,
                "origin_station_id": origin_station_id,
                "destination_station_id": destination_station_id,
            }

        except Exception as e:
            conn.rollback()
            return False, str(e)


def execute_cancellation(booking_id: str, user_id: str) -> tuple[bool, dict | str]:
    """
    Cancels an existing booking and calculates the refund based on service policy.
    Uses a single transaction: booking status update and payment status update
    are committed together.

    Args:
        booking_id: The ID of the booking to cancel.
        user_id: The ID of the user requesting the cancellation.

    Returns:
        (True, result_dict) on success, or (False, error_message) on failure.
    """
    with _connect() as conn:
        try:
            conn.autocommit = False
            with conn.cursor() as cur:
                # Fetch booking details and verify ownership + active status
                cur.execute("""
                    SELECT b.amount_usd, b.travel_date, s.service_type 
                    FROM bookings b
                    JOIN national_rail_schedules s ON b.schedule_id = s.schedule_id
                    WHERE b.booking_id = %s AND b.user_id = %s AND b.status = 'confirmed'
                """, (booking_id, user_id))
                
                row = cur.fetchone()
                if not row:
                    return False, "Booking not found, unauthorized, or already cancelled."
                
                original_amount = float(row[0])
                travel_date_obj = row[1]
                service_type = row[2].lower()
                
                # Refund policy: based on days until travel and service type
                days_until_travel = (travel_date_obj - date.today()).days
                
                if days_until_travel < 0:
                    refund_rate = 0.0  # No refund for past trips
                elif service_type == 'express':
                    refund_rate = 1.0 if days_until_travel > 3 else 0.5
                else:
                    refund_rate = 1.0 if days_until_travel > 1 else 0.75
                    
                refund_amount = original_amount * refund_rate

                cur.execute(
                    "UPDATE bookings SET status = 'cancelled' WHERE booking_id = %s",
                    (booking_id,)
                )
                cur.execute(
                    "UPDATE payments SET status = 'refunded' WHERE booking_id = %s",
                    (booking_id,)
                )
                
            conn.commit()
            return True, {
                "booking_id": booking_id,
                "refund_amount": refund_amount,
                "policy": f"Refund calculated at {refund_rate*100:.0f}% based on {service_type} policy."
            }
        except Exception as e:
            conn.rollback()
            return False, str(e)


# ── AUTHENTICATION QUERIES ────────────────────────────────────────────────────

def register_user(
    email: str,
    first_name: str,
    surname: str,
    year_of_birth: int,
    password: str,
    secret_question: str,
    secret_answer: str,
) -> tuple[bool, str]:
    """
    Registers a new user. Hashes the password with bcrypt before storing.
    Rejects duplicate emails gracefully.

    Returns:
        (True, user_id) on success, or (False, error_message) on failure.
    """
    u_id = "U-" + "".join(random.choices(string.digits, k=4))
    hashed_password = bcrypt.hashpw(
        password.encode('utf-8'), bcrypt.gensalt()
    ).decode('utf-8')

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                # FIX: Insert all required fields including year_of_birth,
                # secret_question, and secret_answer to satisfy NOT NULL constraints
                cur.execute(
                    """
                    INSERT INTO users (
                        user_id, first_name, surname, year_of_birth,
                        email, password, secret_question, secret_answer
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (u_id, first_name, surname, year_of_birth,
                     email, hashed_password, secret_question, secret_answer)
                )
            conn.commit()
        return True, u_id
    except psycopg2.IntegrityError:
        return False, "Email already exists"
    except Exception as e:
        return False, str(e)


def login_user(email: str, password: str) -> Optional[dict]:
    """
    Authenticates a user by email and password using bcrypt verification.
    Returns user dict (without password) on success, None on failure.
    """
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            
            if not row:
                return None
                
            hashed_pwd_from_db = row['password']
            if isinstance(hashed_pwd_from_db, str):
                hashed_pwd_from_db = hashed_pwd_from_db.encode('utf-8')
                
            if bcrypt.checkpw(password.encode('utf-8'), hashed_pwd_from_db):
                user_dict = dict(row)
                user_dict.pop('password', None)
                
                first = user_dict.get('first_name', '')
                last = user_dict.get('surname', '')
                full_name_str = f"{first} {last}".strip()
                user_dict['full_name'] = full_name_str
                user_dict['name'] = full_name_str
                
                return user_dict
            return None


def get_user_secret_question(email: str) -> Optional[str]:
    """Returns the user's registered security question, or None if not found."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT secret_question FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            return row["secret_question"] if row else None


def verify_secret_answer(email: str, answer: str) -> bool:
    """Case-insensitive comparison of the provided answer against the stored value."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT secret_answer FROM users WHERE email = %s", (email,))
            row = cur.fetchone()
            if row and row["secret_answer"].strip().lower() == answer.strip().lower():
                return True
            return False


def update_password(email: str, new_password: str) -> bool:
    """Stores a new bcrypt-hashed password for the given email. Returns True if updated."""
    hashed = bcrypt.hashpw(
        new_password.encode('utf-8'), bcrypt.gensalt()
    ).decode('utf-8')
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE users SET password = %s WHERE email = %s",
                (hashed, email)
            )
            updated = cur.rowcount > 0
        conn.commit()
        return updated

        
# ── VECTOR / RAG QUERIES — do not modify ─────────────────────────────────────

def query_policy_vector_search(embedding: list[float], top_k: int = VECTOR_TOP_K) -> list[dict]:
    """
    Find the most relevant policy documents for a given query embedding.

    Args:
        embedding: Query vector from llm.embed(user_question)
        top_k:     Number of results to return

    Returns:
        List of dicts with title, category, content, and similarity score
    """
    sql = """
        SELECT
            title,
            category,
            content,
            1 - (embedding <=> %s::vector) AS similarity
        FROM policy_documents
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, (vec_str, vec_str, VECTOR_SIMILARITY_THRESHOLD, vec_str, top_k))
            return [dict(row) for row in cur.fetchall()]


def store_policy_document(
    title: str,
    category: str,
    content: str,
    embedding: list[float],
    source_file: str = "",
) -> int:
    """
    Insert a policy document with its embedding into the database.
    Used by skeleton/seed_vectors.py — students don't need to call this directly.

    Returns:
        The new document's id
    """
    sql = """
        INSERT INTO policy_documents (title, category, content, embedding, source_file)
        VALUES (%s, %s, %s, %s::vector, %s)
        RETURNING id
    """
    vec_str = "[" + ",".join(str(x) for x in embedding) + "]"
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (title, category, content, vec_str, source_file))
            doc_id = cur.fetchone()[0]
        conn.commit()
        return doc_id
