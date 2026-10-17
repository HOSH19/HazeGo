"""User and check-in helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from src.config import SGT
from src.db.schema import connect, init_db


def _now_sgt() -> str:
    return datetime.now(ZoneInfo(SGT)).isoformat()


def ensure_user(chat_id: int, username: str | None = None) -> None:
    init_db()
    now = _now_sgt()
    with connect() as conn:
        row = conn.execute("SELECT chat_id FROM users WHERE chat_id = ?", (chat_id,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET username = COALESCE(?, username), updated_at = ? WHERE chat_id = ?",
                (username, now, chat_id),
            )
        else:
            conn.execute(
                "INSERT INTO users (chat_id, username, subscribed, created_at, updated_at) VALUES (?, ?, 1, ?, ?)",
                (chat_id, username, now, now),
            )
        conn.commit()


def set_subscribed(chat_id: int, subscribed: bool) -> None:
    ensure_user(chat_id)
    with connect() as conn:
        conn.execute(
            "UPDATE users SET subscribed = ?, updated_at = ? WHERE chat_id = ?",
            (1 if subscribed else 0, _now_sgt(), chat_id),
        )
        conn.commit()


def list_subscribed_chat_ids() -> list[int]:
    init_db()
    with connect() as conn:
        rows = conn.execute("SELECT chat_id FROM users WHERE subscribed = 1").fetchall()
    return [int(r["chat_id"]) for r in rows]


def set_daily_region(chat_id: int, region: str, checkin_date: str) -> None:
    ensure_user(chat_id)
    now = _now_sgt()
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO daily_checkins (chat_id, checkin_date, region, answered_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(chat_id, checkin_date) DO UPDATE SET
                region = excluded.region,
                answered_at = excluded.answered_at
            """,
            (chat_id, checkin_date, region, now),
        )
        conn.execute(
            "UPDATE users SET last_region = ?, updated_at = ? WHERE chat_id = ?",
            (region, now, chat_id),
        )
        conn.commit()


def get_daily_region(chat_id: int, checkin_date: str) -> str | None:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT region FROM daily_checkins WHERE chat_id = ? AND checkin_date = ?",
            (chat_id, checkin_date),
        ).fetchone()
        if row:
            return str(row["region"])
        user = conn.execute(
            "SELECT last_region FROM users WHERE chat_id = ?", (chat_id,)
        ).fetchone()
    if user and user["last_region"]:
        return str(user["last_region"])
    return None
