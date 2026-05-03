from __future__ import annotations

import sqlite3
import time
from datetime import datetime
from pathlib import Path


def _init_approvals_table(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS approvals (
            approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER,
            gate_type TEXT,
            ref TEXT,
            requested_at TEXT,
            decided_at TEXT,
            decision TEXT,
            notes TEXT
        )
        """
    )


def _decision_log_path(db_path: Path) -> Path:
    return db_path.resolve().parent / "context" / "decision_log.md"


def wait_for_approval(ref: str, db_path: str, timeout_seconds: int) -> bool:
    """Poll sqlite until an approval decision exists or timeout expires."""
    deadline = time.monotonic() + timeout_seconds
    database_path = Path(db_path)

    while time.monotonic() < deadline:
        connection = sqlite3.connect(database_path)
        try:
            _init_approvals_table(connection)
            row = connection.execute(
                """
                SELECT decision
                FROM approvals
                WHERE ref = ? AND decision IS NOT NULL AND decision != ''
                ORDER BY approval_id DESC
                LIMIT 1
                """,
                (ref,),
            ).fetchone()
        finally:
            connection.close()

        if row:
            return str(row[0]).lower() == "approved"
        time.sleep(10)

    return False


def record_decision(
    ref: str,
    gate_type: str,
    decision: str,
    notes: str = "",
    db_path: str = "agent-orchestrator/state.sqlite",
) -> None:
    """Record an approval decision in sqlite and the decision log."""
    database_path = Path(db_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now().isoformat(timespec="seconds")

    connection = sqlite3.connect(database_path)
    try:
        _init_approvals_table(connection)
        connection.execute(
            """
            INSERT INTO approvals (
                run_id,
                gate_type,
                ref,
                requested_at,
                decided_at,
                decision,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (None, gate_type, ref, now, now, decision, notes),
        )
        connection.commit()
    finally:
        connection.close()

    log_path = _decision_log_path(database_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"## [{now}] Gate: {gate_type}\n"
            f"- Ref: {ref}\n"
            f"- Decision: {decision.upper()}\n"
            f"- Notes: {notes}\n\n"
            "---\n\n"
        )
