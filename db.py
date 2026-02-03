# db.py
"""SQLite access with safe schema upgrades and robust inserts."""
import sqlite3
import os
import json
from datetime import datetime
from typing import Dict, Any

DB_PATH = "rowva_data.db"


def _db_file_path() -> str:
    # Keep DB next to this module for portability
    return os.path.join(os.path.dirname(__file__), DB_PATH)


def get_connection():
    return sqlite3.connect(_db_file_path())


def _existing_columns(conn: sqlite3.Connection, table: str):
    cur = conn.execute(f"PRAGMA table_info({table})")
    return {row[1] for row in cur.fetchall()}  # name is 2nd column


def _ensure_columns(conn: sqlite3.Connection, table: str, columns: Dict[str, str]):
    """Add missing columns to `table` using ALTER TABLE ADD COLUMN if needed.
    columns: mapping of column_name -> SQL type+default (e.g., "INTEGER DEFAULT 0")
    """
    existing = _existing_columns(conn, table)
    for col, definition in columns.items():
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {definition}")


def init_db():
    """Create tables and migrate schema (idempotent)."""
    conn = get_connection()
    cur = conn.cursor()

    # Create base table with a minimal safe schema so the table exists
    cur.execute('''
        CREATE TABLE IF NOT EXISTS daily_records (
            date TEXT PRIMARY KEY,
            raw_text TEXT NOT NULL,
            parsed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            cash_in_hand REAL DEFAULT 0.0
        )
    ''')

    # Ensure additional columns exist with sensible defaults
    _ensure_columns(conn, 'daily_records', {
        # Stats
        'tables_count': 'INTEGER DEFAULT 0',
        'arrests_count': 'INTEGER DEFAULT 0',
        # Income breakdown
        'income_json': "TEXT DEFAULT '{}'",
        'total_income': 'REAL DEFAULT 0.0',
        # Expense breakdown
        'expenses_json': "TEXT DEFAULT '{}'",
        'total_expenses': 'REAL DEFAULT 0.0',
        'shared_expense': 'REAL DEFAULT 0.0',
        # Final figures
        'declared_total_income': 'REAL',
        'declared_total_expenses': 'REAL'
    })

    cur.execute('''
        CREATE TABLE IF NOT EXISTS rl_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            issue_type TEXT NOT NULL,
            description TEXT,
            user_correction TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(date) REFERENCES daily_records(date)
        )
    ''')
        # Corrections table: supervised learning / audit trail
    cur.execute('''
        CREATE TABLE IF NOT EXISTS corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,                 -- record date (YYYY-MM-DD)
            raw_segment TEXT NOT NULL,          -- snippet of original text
            parsed_label TEXT,                  -- what parser classified it as
            correct_label TEXT NOT NULL,        -- user/Gemini correction
            source TEXT NOT NULL,               -- 'user' | 'gemini'
            confidence REAL DEFAULT 0.0,        -- optional confidence score
            applied INTEGER DEFAULT 0,          -- 0 = not applied to rules, 1 = applied
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Learned rules proposed and (optionally) approved
    cur.execute('''
        CREATE TABLE IF NOT EXISTS learned_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rule_key TEXT NOT NULL UNIQUE,      -- short rule id
            rule_json TEXT NOT NULL,            -- canonical JSON rule
            description TEXT,
            source TEXT,                        -- e.g., 'gemini','user'
            approved INTEGER DEFAULT 0,         -- 0 = suggested, 1 = approved
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')


    conn.commit()
    conn.close()


def _normalize_json_field(val):
    """Accept a dict or JSON string and return a JSON string representation."""
    if val is None:
        return json.dumps({})
    if isinstance(val, str):
        # If already a JSON string, try to load to validate / canonicalize
        try:
            obj = json.loads(val)
            return json.dumps(obj)
        except json.JSONDecodeError:
            # Not valid JSON, store as raw string under a special key
            return json.dumps({"_raw": val})
    if isinstance(val, dict):
        return json.dumps(val)
    # Fallback
    try:
        return json.dumps(dict(val))
    except Exception:
        return json.dumps({})


def save_daily_record(record: Dict[str, Any]):
    """Save parsed day to DB. Performs a schema check and will add missing
    columns if older DB file lacks them (fixes "no column named tables_count")."""
    # Normalize record values and ensure JSON fields are strings
    rec = {
        'date': record['date'],
        'raw_text': record.get('raw_text', ''),
        'tables_count': int(record.get('tables_count') or 0),
        'arrests_count': int(record.get('arrests_count') or 0),
        'income_json': _normalize_json_field(record.get('income_json')),
        'total_income': float(record.get('total_income') or 0.0),
        'expenses_json': _normalize_json_field(record.get('expenses_json')),
        'total_expenses': float(record.get('total_expenses') or 0.0),
        'shared_expense': float(record.get('shared_expense') or 0.0),
        'declared_total_income': (None if record.get('declared_total_income') is None else float(record.get('declared_total_income'))),
        'declared_total_expenses': (None if record.get('declared_total_expenses') is None else float(record.get('declared_total_expenses'))),
        'cash_in_hand': float(record.get('cash_in_hand') or 0.0)
    }

    conn = get_connection()
    try:
        cur = conn.cursor()
        # If the DB is old and missing columns, _ensure_columns will add them
        _ensure_columns(conn, 'daily_records', {
            'tables_count': 'INTEGER DEFAULT 0',
            'arrests_count': 'INTEGER DEFAULT 0',
            'income_json': "TEXT DEFAULT '{}'",
            'total_income': 'REAL DEFAULT 0.0',
            'expenses_json': "TEXT DEFAULT '{}'",
            'total_expenses': 'REAL DEFAULT 0.0',
            'shared_expense': 'REAL DEFAULT 0.0',
            'declared_total_income': 'REAL',
            'declared_total_expenses': 'REAL'
        })

        cur.execute('''
            INSERT OR REPLACE INTO daily_records
            (date, raw_text, tables_count, arrests_count, income_json, total_income,
             expenses_json, total_expenses, shared_expense, declared_total_income,
             declared_total_expenses, cash_in_hand)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            rec['date'], rec['raw_text'], rec['tables_count'], rec['arrests_count'],
            rec['income_json'], rec['total_income'], rec['expenses_json'], rec['total_expenses'],
            rec['shared_expense'], rec['declared_total_income'], rec['declared_total_expenses'],
            rec['cash_in_hand']
        ))
        conn.commit()
    finally:
        conn.close()


def get_weekly_data(week_start: str):
    """Get 7 days of data starting from week_start (YYYY-MM-DD)"""
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT date, total_income, total_expenses, cash_in_hand
        FROM daily_records
        WHERE date BETWEEN ? AND date(?, '+6 days')
        ORDER BY date
    ''', (week_start, week_start))
    rows = c.fetchall()
    conn.close()
    return rows

def log_correction(date: str, raw_segment: str, parsed_label: str, correct_label: str,
                   source: str = "user", confidence: float = 0.0):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO corrections (date, raw_segment, parsed_label, correct_label, source, confidence)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (date, raw_segment, parsed_label, correct_label, source, confidence))
    conn.commit()
    conn.close()

def get_unapplied_corrections(limit: int = 100):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        SELECT id, date, raw_segment, parsed_label, correct_label, source, confidence
        FROM corrections
        WHERE applied = 0
        ORDER BY created_at ASC
        LIMIT ?
    ''', (limit,))
    rows = c.fetchall()
    conn.close()
    return rows

def mark_corrections_applied(ids):
    if not ids:
        return
    conn = get_connection()
    c = conn.cursor()
    c.execute(f'''
        UPDATE corrections SET applied = 1 WHERE id IN ({','.join('?' for _ in ids)})
    ''', ids)
    conn.commit()
    conn.close()

def add_learned_rule(rule_key: str, rule_json: str, description: str = "", source: str = "gemini", approved: int = 0):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO learned_rules (rule_key, rule_json, description, source, approved)
        VALUES (?, ?, ?, ?, ?)
    ''', (rule_key, rule_json, description, source, approved))
    conn.commit()
    conn.close()

def get_learned_rules(approved_only: bool = True):
    conn = get_connection()
    c = conn.cursor()
    if approved_only:
        c.execute('SELECT rule_key, rule_json, description FROM learned_rules WHERE approved = 1')
    else:
        c.execute('SELECT id, rule_key, rule_json, description, approved FROM learned_rules ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows

def log_rl_feedback(date: str, issue_type: str, desc: str, correction: str = ""):
    conn = get_connection()
    c = conn.cursor()
    c.execute('''
        INSERT INTO rl_feedback (date, issue_type, description, user_correction)
        VALUES (?, ?, ?, ?)
    ''', (date, issue_type, desc, correction))
    conn.commit()
    conn.close()


# Ensure DB exists and has latest schema when module is imported
init_db()