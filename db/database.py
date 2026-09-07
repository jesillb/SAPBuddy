"""SQLite connection and schema management for SAP BRIM Targeting Tool."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "sapbuddy.db"


def get_db_path() -> str:
    return os.environ.get("SAPBUDDY_DB_PATH", str(DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def connection_scope():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    domain TEXT,
    hq_country TEXT,
    hq_city TEXT,
    other_sites TEXT,
    industry TEXT,
    employee_range TEXT,
    revenue_range_eur TEXT,
    sap_status TEXT DEFAULT 'unknown',
    sap_signals TEXT,
    likely_modules TEXT,
    module_confidence TEXT,
    brim_score INTEGER DEFAULT 0,
    brim_score_reason TEXT,
    brim_components_likely TEXT,
    brim_evidence TEXT,
    recent_events TEXT,
    last_event_date TEXT,
    s4_migration_status TEXT DEFAULT 'unknown',
    einvoicing_pressure TEXT DEFAULT 'low',
    priority_tier TEXT DEFAULT 'C',
    recommended_action TEXT,
    outreach_angles TEXT,
    last_contacted_at TEXT,
    notes TEXT,
    tags TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_companies_priority_tier ON companies(priority_tier);
CREATE INDEX IF NOT EXISTS idx_companies_brim_score ON companies(brim_score);
CREATE INDEX IF NOT EXISTS idx_companies_hq_country ON companies(hq_country);
CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_name_domain ON companies(name, COALESCE(domain, ''));
"""


def init_db() -> None:
    with connection_scope() as conn:
        conn.executescript(SCHEMA)
