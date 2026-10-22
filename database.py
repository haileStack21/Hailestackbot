
import os
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    return psycopg.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        dbname=os.getenv("DB_NAME", "hailestack"),
        user=os.getenv("DB_USER", "hailestack_user"),
        password=os.getenv("DB_PASSWORD"),
        row_factory=dict_row,
    )


def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                telegram_id BIGINT NOT NULL,
                telegram_username TEXT,
                full_name VARCHAR(100) NOT NULL,
                stream VARCHAR(100) NOT NULL,
                department VARCHAR(100) NOT NULL,
                payment_reference VARCHAR(120) NOT NULL UNIQUE,
                payment_status VARCHAR(20) NOT NULL DEFAULT 'pending'
                    CHECK (
                        payment_status IN ('pending', 'approved', 'rejected')
                    ),
                registered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)


def save_student(
    telegram_id,
    telegram_username,
    full_name,
    stream,
    department,
    payment_reference,
):
    with get_connection() as conn:
        row = conn.execute("""
            INSERT INTO students (
                telegram_id, telegram_username, full_name,
                stream, department, payment_reference
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            telegram_id,
            telegram_username,
            full_name,
            stream,
            department,
            payment_reference,
        )).fetchone()

        return row["id"]


def get_pending_students(limit=20):
    with get_connection() as conn:
        return conn.execute("""
            SELECT id, telegram_id, telegram_username,
                   full_name, stream, department,
                   payment_reference, registered_at
            FROM students
            WHERE payment_status = 'pending'
            ORDER BY registered_at ASC
            LIMIT %s
        """, (limit,)).fetchall()


def get_student(student_id):
    with get_connection() as conn:
        return conn.execute("""
            SELECT id, telegram_id, telegram_username,
                   full_name, stream, department,
                   payment_reference, payment_status
            FROM students
            WHERE id = %s
        """, (student_id,)).fetchone()


def set_student_status(student_id, new_status):
    if new_status not in ("approved", "rejected"):
        raise ValueError("Invalid student status")

    with get_connection() as conn:
        return conn.execute("""
            UPDATE students
            SET payment_status = %s
            WHERE id = %s AND payment_status = 'pending'
            RETURNING id, telegram_id, full_name,
                      payment_reference, payment_status
        """, (new_status, student_id)).fetchone()
