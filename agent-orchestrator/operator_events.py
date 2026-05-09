from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


IN_FLIGHT_EVENT_TYPES = {"resume_received", "validating", "medium_review_running"}
TERMINAL_EVENT_TYPES = {
    "prompt_ready",
    "validation_failed",
    "medium_review_done",
    "paused",
    "task_done",
    "approval_required",
}


def now_timestamp() -> str:
    """Return a compact local timestamp for operator events."""
    return datetime.now().isoformat(timespec="seconds")


def init_operator_tables(connection: sqlite3.Connection) -> None:
    """Create the operator event and UI state tables if needed."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_events (
            event_id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            event_type TEXT NOT NULL,
            task_id INTEGER,
            phase TEXT,
            title TEXT,
            status TEXT,
            summary TEXT,
            details_json TEXT,
            delivered_at TEXT
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS operator_ui_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """
    )


def _connect(db_path: str | Path) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    init_operator_tables(connection)
    return connection


def record_event(
    db_path: str | Path,
    event_type: str,
    task_id: int | None = None,
    phase: str | None = None,
    title: str | None = None,
    status: str | None = None,
    summary: str | None = None,
    details: dict[str, Any] | None = None,
) -> int:
    """Append a compact event for the Discord operator card."""
    connection = _connect(db_path)
    try:
        cursor = connection.execute(
            """
            INSERT INTO operator_events (
                created_at,
                event_type,
                task_id,
                phase,
                title,
                status,
                summary,
                details_json,
                delivered_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
            """,
            (
                now_timestamp(),
                event_type,
                task_id,
                phase,
                title,
                status,
                summary,
                json.dumps(details or {}, sort_keys=True),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def recent_events(connection: sqlite3.Connection, limit: int = 8) -> list[sqlite3.Row]:
    """Return recent operator events in chronological order."""
    rows = connection.execute(
        """
        SELECT *
        FROM operator_events
        ORDER BY event_id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return list(reversed(rows))


def undelivered_events(connection: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    """Return events that the Discord listener has not rendered yet."""
    return connection.execute(
        """
        SELECT *
        FROM operator_events
        WHERE delivered_at IS NULL
        ORDER BY event_id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()


def mark_delivered(connection: sqlite3.Connection, event_ids: list[int]) -> None:
    """Mark rendered events as delivered."""
    if not event_ids:
        return
    placeholders = ",".join("?" for _ in event_ids)
    connection.execute(
        f"UPDATE operator_events SET delivered_at = ? WHERE event_id IN ({placeholders})",
        (now_timestamp(), *event_ids),
    )
    connection.commit()


def latest_event(connection: sqlite3.Connection) -> sqlite3.Row | None:
    """Return the newest operator event."""
    return connection.execute(
        """
        SELECT *
        FROM operator_events
        ORDER BY event_id DESC
        LIMIT 1
        """
    ).fetchone()


def operator_in_flight(connection: sqlite3.Connection) -> bool:
    """Return whether the latest operator event represents active work."""
    row = latest_event(connection)
    if row is None:
        return False
    event_type = str(row["event_type"])
    if event_type in TERMINAL_EVENT_TYPES:
        return False
    return event_type in IN_FLIGHT_EVENT_TYPES


def set_ui_state(connection: sqlite3.Connection, key: str, value: str) -> None:
    """Persist a small Discord UI state value."""
    connection.execute(
        """
        INSERT OR REPLACE INTO operator_ui_state (key, value)
        VALUES (?, ?)
        """,
        (key, value),
    )
    connection.commit()


def get_ui_state(connection: sqlite3.Connection, key: str) -> str | None:
    """Read a small Discord UI state value."""
    row = connection.execute(
        "SELECT value FROM operator_ui_state WHERE key = ?",
        (key,),
    ).fetchone()
    if row is None:
        return None
    return str(row["value"])
