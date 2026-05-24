# -*- coding: utf-8 -*-
import sqlite3
import os
import datetime

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "socialintent.db")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize SQLite database tables if they do not exist."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # 1. Create licenses table with transaction_id to link with Stripe sessions
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS licenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        license_key TEXT UNIQUE NOT NULL,
        status TEXT NOT NULL DEFAULT 'active', -- 'active', 'disabled'
        email TEXT NOT NULL,
        transaction_id TEXT, -- Stripe Session ID
        created_at TEXT NOT NULL,
        activated_at TEXT
    )
    """)
    
    # 2. Create transactions table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id TEXT UNIQUE NOT NULL,
        email TEXT NOT NULL,
        amount INTEGER NOT NULL,
        status TEXT NOT NULL, -- 'completed', 'pending', 'failed'
        created_at TEXT NOT NULL
    )
    """)
    
    conn.commit()
    conn.close()
    print("Database initialized successfully at:", DB_PATH)

def create_license(license_key, email, transaction_id=None):
    """Insert a new active license key into the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    created_at = datetime.datetime.now().isoformat()
    try:
        cursor.execute(
            "INSERT INTO licenses (license_key, status, email, transaction_id, created_at) VALUES (?, 'active', ?, ?, ?)",
            (license_key, email, transaction_id, created_at)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def get_license_by_transaction(transaction_id):
    """Retrieve license key information by its transaction_id (Stripe Session ID)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM licenses WHERE transaction_id = ?",
        (transaction_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None

def validate_license(license_key):
    """Check if the license key exists and is active."""
    conn = get_db_connection()
    cursor = conn.cursor()
    row = cursor.execute(
        "SELECT * FROM licenses WHERE license_key = ? AND status = 'active'",
        (license_key,)
    ).fetchone()
    
    if row:
        # Update activated_at timestamp if not set yet
        if not row["activated_at"]:
            activated_at = datetime.datetime.now().isoformat()
            cursor.execute(
                "UPDATE licenses SET activated_at = ? WHERE license_key = ?",
                (activated_at, license_key)
            )
            conn.commit()
        conn.close()
        return True
        
    conn.close()
    return False

def record_transaction(transaction_id, email, amount, status):
    """Record payment transaction history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    created_at = datetime.datetime.now().isoformat()
    try:
        cursor.execute(
            "INSERT INTO transactions (transaction_id, email, amount, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (transaction_id, email, amount, status, created_at)
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

