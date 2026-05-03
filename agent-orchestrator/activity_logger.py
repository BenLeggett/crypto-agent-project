from __future__ import annotations

import sqlite3
from pathlib import Path


def _normalize_timestamp(timestamp: str) -> str:
    """Render ISO-like timestamps in the activity heading format."""
    normalized = timestamp.strip().replace("T", " ").replace("Z", "")
    return normalized.split(".")[0]


def _format_model(model_tier: str, model_name: str) -> str:
    """Build the model display line."""
    if model_name:
        return f"{model_tier} ({model_name})"
    return model_tier or "unknown"


def _format_activity_entry(record: dict) -> str:
    """Create one append-only ACTIVITY.md entry."""
    timestamp = _normalize_timestamp(str(record.get("timestamp", "")))
    run_id = str(record.get("run_id", "")).zfill(4)
    phase = record.get("phase", "unknown")
    task_id = record.get("task_id", "unknown")
    action = record.get("action", "")
    model_tier = str(record.get("model_tier", ""))
    model_name = str(record.get("model_name", ""))
    outcome = record.get("outcome", "")
    notes = record.get("notes", "")
    source = record.get("source", "Agent Orchestrator")
    validation = record.get("validation", "Not provided")

    return (
        f"## [{timestamp}] Run {run_id} · {phase} · Task {task_id}\n\n"
        f"**Source:** {source}  \n"
        f"**Action:** {action}  \n"
        f"**Model:** {_format_model(model_tier, model_name)}  \n"
        f"**Outcome:** {outcome}  \n"
        f"**Validation:** {validation}  \n"
        f"**Notes:** {notes}\n\n"
        "---\n"
    )


def log_activity(record: dict, activity_path: str = "ACTIVITY.md") -> None:
    """Append a structured activity entry, creating the file if needed."""
    path = Path(activity_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        if path.exists() and path.stat().st_size > 0:
            handle.write("\n")
        handle.write(_format_activity_entry(record))


def log_run(record: dict, db_path: str = "agent-orchestrator/state.sqlite") -> None:
    """Insert or replace a run record in the sqlite runs table."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                run_id INTEGER PRIMARY KEY,
                timestamp TEXT,
                task_id INTEGER,
                model_tier TEXT,
                model_name TEXT,
                action TEXT,
                outcome TEXT,
                prompt_tokens INTEGER,
                completion_tokens INTEGER,
                cost_estimate_usd REAL
            )
            """
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO runs (
                run_id,
                timestamp,
                task_id,
                model_tier,
                model_name,
                action,
                outcome,
                prompt_tokens,
                completion_tokens,
                cost_estimate_usd
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.get("run_id"),
                record.get("timestamp"),
                record.get("task_id"),
                record.get("model_tier"),
                record.get("model_name"),
                record.get("action"),
                record.get("outcome"),
                record.get("prompt_tokens"),
                record.get("completion_tokens"),
                record.get("cost_estimate_usd"),
            ),
        )
        connection.commit()
    finally:
        connection.close()
