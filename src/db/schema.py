"""SQLite schema for Telegram user prefs and daily check-ins."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.config import DATABASE_PATH, DATA_DIR


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    chat_id INTEGER PRIMARY KEY,
    username TEXT,
    subscribed INTEGER NOT NULL DEFAULT 1,
    last_region TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS daily_checkins (
    chat_id INTEGER NOT NULL,
    checkin_date TEXT NOT NULL,
    region TEXT NOT NULL,
    answered_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, checkin_date),
    FOREIGN KEY (chat_id) REFERENCES users(chat_id)
);
"""


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()
