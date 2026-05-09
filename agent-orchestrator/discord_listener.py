from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
from contextlib import closing, suppress
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for non-venv interpreters
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        _ = (args, kwargs)
        return False

MODULE_ROOT = Path(__file__).resolve().parent
if str(MODULE_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE_ROOT))

import prompt_runner
import operator_events
from model_router import ModelTier


DEFAULT_DB_PATH = str(Path(__file__).with_name("state.sqlite"))
MOCK_MODE_MESSAGE = "Running in mock mode \u2014 bot token not configured"
DISCORD_RESPONSE_LIMIT = 1900
CARD_FIELD_LIMIT = 650
CARD_PROGRESS_LIMIT = 420
UNKNOWN_COMMAND_MESSAGE = (
    "Unknown command. Available: !status !approve !reject !pause !resume !explain"
)
MEDIUM_REVIEW_START_PREFIX = "[ORCHESTRATOR - MEDIUM REVIEW START]"
MEDIUM_REVIEW_DONE_PREFIXES = (
    "[ORCHESTRATOR - MEDIUM LOCAL REVIEW]",
    "[ORCHESTRATOR - MEDIUM REVIEW UNAVAILABLE]",
    "[ORCHESTRATOR - DIAGNOSIS UNAVAILABLE]",
)
COMMAND_ALIASES = {
    "!reusme": "!resume",
}


def _load_local_env() -> None:
    """Load the orchestrator-local .env file when present."""
    load_dotenv(Path(__file__).with_name(".env"))


def _connect(db_path: str) -> sqlite3.Connection:
    """Open the SQLite database and ensure listener-owned tables exist."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id INTEGER PRIMARY KEY,
            phase TEXT,
            title TEXT,
            status TEXT,
            attempts INTEGER DEFAULT 0,
            last_run_id INTEGER,
            notes TEXT
        )
        """
    )
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
    operator_events.init_operator_tables(connection)
    return connection


def _now_timestamp() -> str:
    """Return a stable wall-clock timestamp for SQLite inserts."""
    return datetime.now().isoformat(timespec="seconds")


def _normalize_status(status: str | None) -> str:
    """Convert a task status into a Discord-friendly label."""
    if not status:
        return "unknown"
    return status.replace("_", " ")


def _validation_label(task_status: str | None) -> str:
    """Render validation state from the persisted task status."""
    normalized = (task_status or "").strip().lower()
    if normalized == "done":
        return "passed"
    if normalized == "failed":
        return "failed"
    if normalized == "in_progress":
        return "awaiting manual application or validation"
    if normalized == "pending":
        return "pending"
    if normalized == "skipped":
        return "n/a"
    return "unknown"


def _next_action_label(task_status: str | None) -> str:
    """Return the most useful operator action for the current task status."""
    normalized = (task_status or "").strip().lower()
    if normalized == "failed":
        return "inspect the failure, repair manually, then use !resume to re-run validation"
    if normalized == "in_progress":
        return "apply last_prompt.md if needed, then use !resume to validate"
    if normalized == "pending":
        return "wait for the orchestrator to process this task"
    return "use !status or !explain to inspect the current state"


def _format_status_message(
    phase: str,
    task_id: str | int,
    task_title: str,
    task_status: str | None,
) -> str:
    """Return the status update format defined in the plan doc."""
    human_status = _normalize_status(task_status)
    return (
        f"[ORCHESTRATOR] {phase} \u00b7 Task {task_id}: {task_title}\n"
        f"Status: {human_status}\n"
        "Model used: n/a\n"
        f"Validation: {_validation_label(task_status)}\n"
        f"Next: {_next_action_label(task_status)}"
    )


def _read_status(connection: sqlite3.Connection) -> str:
    """Read the current phase and first pending task from the tasks table."""
    current_row = connection.execute(
        """
        SELECT task_id, phase, title, status
        FROM tasks
        WHERE status NOT IN ('done', 'skipped')
        ORDER BY
            CASE status WHEN 'in_progress' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
            phase,
            task_id
        LIMIT 1
        """
    ).fetchone()

    if current_row is None:
        return (
            "[ORCHESTRATOR] No active phase \u00b7 Task n/a: No pending tasks\n"
            "Status: idle\n"
            "Model used: n/a\n"
            "Validation: n/a\n"
            "Next: queue a task or advance the phase"
        )

    pending_row = connection.execute(
        """
        SELECT task_id, phase, title, status
        FROM tasks
        WHERE phase = ? AND status = 'pending'
        ORDER BY task_id
        LIMIT 1
        """,
        (current_row["phase"],),
    ).fetchone()

    task_row = current_row
    if current_row["status"] not in {"in_progress", "failed"} and pending_row is not None:
        task_row = pending_row
    return _format_status_message(
        phase=str(current_row["phase"]),
        task_id=task_row["task_id"],
        task_title=str(task_row["title"]),
        task_status=task_row["status"],
    )


def _active_task_row(connection: sqlite3.Connection) -> sqlite3.Row | None:
    """Return the active task row used by the operator card."""
    return connection.execute(
        """
        SELECT task_id, phase, title, status, notes
        FROM tasks
        WHERE status NOT IN ('done', 'skipped')
        ORDER BY
            CASE status WHEN 'in_progress' THEN 0 WHEN 'failed' THEN 1 WHEN 'pending' THEN 2 ELSE 3 END,
            phase,
            task_id
        LIMIT 1
        """
    ).fetchone()


def _event_label(event_type: str, status: str | None = None) -> str:
    """Render one compact timeline label."""
    if event_type == "run_started":
        return "Loop started"
    if event_type == "prompt_ready":
        return "Prompt ready"
    if event_type == "resume_received":
        return "Resume selected"
    if event_type == "validating":
        return "Validating"
    if event_type == "validation_failed":
        return "Failed"
    if event_type == "medium_review_running":
        return "Reviewing diagnosis"
    if event_type == "medium_review_done":
        return "Diagnosis unavailable" if status == "diagnosis_unavailable" else "Diagnosis ready"
    if event_type == "approval_required":
        return "Approval needed"
    if event_type == "paused":
        return "Paused"
    if event_type == "task_done":
        return "Done"
    return event_type.replace("_", " ").title()


def _collapse_timeline_labels(labels: list[str], limit: int = 5) -> str:
    """Collapse repeated adjacent timeline labels and emphasize the current step."""
    collapsed: list[tuple[str, int]] = []
    for label in labels:
        if collapsed and collapsed[-1][0] == label:
            previous_label, count = collapsed[-1]
            collapsed[-1] = (previous_label, count + 1)
            continue
        collapsed.append((label, 1))
    collapsed = collapsed[-limit:]
    rendered = [f"{label} x{count}" if count > 1 else label for label, count in collapsed]
    if rendered:
        rendered[-1] = f"**{rendered[-1]}**"
    return " -> ".join(rendered) or "No operator events yet"


def _card_status(latest_event: sqlite3.Row | None, task_status: str | None) -> str:
    """Return the task card headline status."""
    if latest_event is not None:
        event_type = str(latest_event["event_type"])
        status = str(latest_event["status"] or "")
        if event_type == "medium_review_running":
            return "Reviewing diagnosis"
        if event_type == "validating":
            return "Validating"
        if event_type == "validation_failed":
            return "Failed validation"
        if event_type == "medium_review_done":
            return "Failed validation"
        if event_type == "prompt_ready":
            return "Prompt ready"
        if event_type == "approval_required":
            return "Approval required"
        if event_type == "task_done" or status == "done":
            return "Complete"
    if (task_status or "").strip().lower() == "failed":
        return "Failed validation"
    return _normalize_status(task_status).title()


def _card_excerpt(text: str, limit: int = CARD_FIELD_LIMIT) -> str:
    """Trim card fields to stable, readable lengths."""
    stripped = " ".join((text or "").strip().split())
    if len(stripped) <= limit:
        return stripped or "None yet."
    return f"{stripped[: limit - 15].rstrip()} ...[truncated]"


def _format_file_hints(text: str) -> str:
    """Highlight common local file/config names inside Discord markdown."""
    placeholders = {
        ".env.example": "__ENV_EXAMPLE__",
        ".env": "__ENV_FILE__",
        "last_prompt.md": "__LAST_PROMPT__",
        "ACTIVITY.MD": "__ACTIVITY__",
    }
    formatted = text
    for token, placeholder in placeholders.items():
        formatted = formatted.replace(token, placeholder)
    for token, placeholder in placeholders.items():
        formatted = formatted.replace(placeholder, f"`{token}`")
    return formatted


def _friendly_summary(summary: str) -> str:
    """Convert terse machine summaries into operator-friendly card text."""
    cleaned = _format_file_hints(summary.strip())
    lowered = cleaned.lower()
    if "forbidden path modified" in lowered and "`.env`" in cleaned:
        return (
            "Validation failed because `.env` was modified, which is forbidden by "
            "the deterministic validator."
        )
    if "medium local review returned an empty response" in lowered:
        return (
            "Diagnosis unavailable: the medium model returned an empty response. "
            "Deterministic validation is still authoritative."
        )
    if cleaned.startswith("Diagnosis unavailable:"):
        return cleaned.replace("Medium local review unavailable:", "medium review unavailable:")
    return cleaned


def _latest_finding(events: list[sqlite3.Row]) -> str:
    """Return the latest failure or diagnosis summary for the card."""
    for row in reversed(events):
        event_type = str(row["event_type"])
        if event_type in {"medium_review_done", "validation_failed"}:
            summary = str(row["summary"] or "").strip()
            if summary:
                return _card_excerpt(_friendly_summary(summary))
    return "No findings yet."


def _next_card_action(connection: sqlite3.Connection, latest_event: sqlite3.Row | None, task_status: str | None) -> str:
    """Return one operator-facing next action for the card."""
    if operator_events.operator_in_flight(connection):
        if latest_event is not None and str(latest_event["event_type"]) == "medium_review_running":
            return "Wait for the medium review result. Buttons will return when it finishes."
        return "Wait for the current step to finish."
    if latest_event is not None and str(latest_event["event_type"]) == "approval_required":
        return "Use Approve or Reject after reviewing the request."
    normalized = (task_status or "").strip().lower()
    if normalized == "failed":
        finding = _latest_finding(operator_events.recent_events(connection, limit=7))
        if "`.env`" in finding:
            return "Move local config out of tracked `.env` changes, then press Resume to re-run validation."
        return "Repair manually, then use Resume to re-run validation."
    if normalized == "in_progress":
        return "Apply last_prompt.md if needed, then use Resume to validate."
    if normalized == "pending":
        return "Wait for the run loop to prepare the prompt."
    return "Use Status or Explain to inspect the current state."


def _legacy_task_run_card(db_path: str) -> str:
    """Legacy text card retained for compatibility during transition."""
    with closing(_connect(db_path)) as connection:
        events = operator_events.recent_events(connection, limit=7)
        latest_event = events[-1] if events else None
        task_row = _active_task_row(connection)
        task_id = task_row["task_id"] if task_row is not None else (
            latest_event["task_id"] if latest_event is not None and latest_event["task_id"] is not None else "n/a"
        )
        title = str(task_row["title"]) if task_row is not None else (
            str(latest_event["title"]) if latest_event is not None and latest_event["title"] else "No active task"
        )
        task_status = str(task_row["status"]) if task_row is not None else (
            str(latest_event["status"]) if latest_event is not None and latest_event["status"] else "idle"
        )
        status = _card_status(latest_event, task_status)
        timeline = " -> ".join(
            _event_label(str(row["event_type"]), str(row["status"] or ""))
            for row in events
        ) or "No operator events yet"
        current = str(latest_event["summary"] or "").strip() if latest_event is not None else "Waiting for the orchestrator."
        finding = _latest_finding(events)
        next_action = _next_card_action(connection, latest_event, task_status)

    return _text_excerpt_from_string(
        "\n".join(
            [
                f"Task {task_id} · {title} · {status}",
                "",
                f"Timeline: {timeline}",
                f"Now: {current}",
                f"Finding: {finding}",
                f"Next: {next_action}",
            ]
        ),
        limit=DISCORD_RESPONSE_LIMIT,
    )

def _task_run_card_payload(db_path: str) -> dict[str, object]:
    """Build stable content and fields for the Discord task run card."""
    with closing(_connect(db_path)) as connection:
        events = operator_events.recent_events(connection, limit=7)
        latest_event = events[-1] if events else None
        task_row = _active_task_row(connection)
        task_id = task_row["task_id"] if task_row is not None else (
            latest_event["task_id"] if latest_event is not None and latest_event["task_id"] is not None else "n/a"
        )
        title = str(task_row["title"]) if task_row is not None else (
            str(latest_event["title"]) if latest_event is not None and latest_event["title"] else "No active task"
        )
        task_status = str(task_row["status"]) if task_row is not None else (
            str(latest_event["status"]) if latest_event is not None and latest_event["status"] else "idle"
        )
        status = _card_status(latest_event, task_status)
        timeline = _collapse_timeline_labels(
            [_event_label(str(row["event_type"]), str(row["status"] or "")) for row in events]
        )
        current = _friendly_summary(
            str(latest_event["summary"] or "").strip()
            if latest_event is not None
            else "Waiting for the orchestrator."
        )
        finding = _latest_finding(events)
        next_action = _next_card_action(connection, latest_event, task_status)

    return {
        "content": "[ORCHESTRATOR] Task Run Card",
        "title": _card_excerpt(f"Task {task_id} | {title}", limit=240),
        "status": f"**{_card_excerpt(status, limit=120)}**",
        "progress": _card_excerpt(timeline, limit=CARD_PROGRESS_LIMIT),
        "current": _card_excerpt(current),
        "finding": _card_excerpt(finding),
        "next": _card_excerpt(_format_file_hints(next_action)),
    }


def _task_run_card(db_path: str) -> str:
    """Render the single operator cockpit card for mock/status output."""
    payload = _task_run_card_payload(db_path)
    return _text_excerpt_from_string(
        "\n".join(
            [
                str(payload["title"]),
                "",
                f"Status: {payload['status']}",
                "",
                "Progress:",
                str(payload["progress"]),
                "",
                "Current Step:",
                str(payload["current"]),
                "",
                "Finding:",
                str(payload["finding"]),
                "",
                "Next Action:",
                str(payload["next"]),
            ]
        ),
        limit=DISCORD_RESPONSE_LIMIT,
    )


def _read_paused_state(connection: sqlite3.Connection) -> str:
    """Return the current pause state without changing it."""
    row = connection.execute(
        "SELECT value FROM settings WHERE key = 'paused'"
    ).fetchone()
    if row is None:
        return "unknown"
    return "paused" if str(row["value"]) == "1" else "running"


def _activity_entries(activity_path: Path, max_entries: int = 3) -> str:
    """Return the latest activity entries for compact operator context."""
    if not activity_path.exists():
        return "No activity log found."

    lines = activity_path.read_text(encoding="utf-8", errors="replace").splitlines()
    entries: list[str] = []
    current: list[str] = []
    for line in lines:
        if line.startswith("## "):
            if current:
                entries.append("\n".join(current).strip())
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        entries.append("\n".join(current).strip())
    if not entries:
        return "No activity entries found."
    return "\n\n".join(entries[-max_entries:])


def _text_excerpt(path: Path, limit: int = 1200) -> str:
    """Read a compact excerpt without mutating prompt files."""
    if not path.exists():
        return f"{path.name} not found."
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    if not text:
        return f"{path.name} is empty."
    if len(text) <= limit:
        return text
    return f"{text[: limit - 15].rstrip()} ...[truncated]"


def _text_excerpt_from_string(text: str, limit: int = DISCORD_RESPONSE_LIMIT) -> str:
    """Trim generated responses for Discord."""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[: limit - 15].rstrip()} ...[truncated]"


def _split_discord_messages(text: str, limit: int = DISCORD_RESPONSE_LIMIT) -> list[str]:
    """Split long responses across Discord messages without losing content."""
    stripped = text.strip() or "(empty response)"
    if len(stripped) <= limit:
        return [stripped]

    chunks: list[str] = []
    remaining = stripped
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, limit)
        if split_at < limit // 2:
            split_at = remaining.rfind(" ", 0, limit)
        if split_at < limit // 2:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    return chunks


def _loading_message_for_command(command: str, args: list[str]) -> str:
    """Return action-specific progress text for Discord operators."""
    if command == "!explain":
        return "[ORCHESTRATOR] Explaining the latest action... checking SQLite state, activity, prompt context, and the local model."
    if command == "!status":
        return "[ORCHESTRATOR] Reading current task state..."
    if command == "!resume":
        return "[ORCHESTRATOR] Resuming the loop... clearing the pause flag."
    if command == "!pause":
        return "[ORCHESTRATOR] Pausing the loop... setting the pause flag."
    if command == "!approve":
        ref = args[0] if args else "<missing-ref>"
        return f"[ORCHESTRATOR] Recording approval for {ref}..."
    if command == "!reject":
        ref = args[0] if args else "<missing-ref>"
        return f"[ORCHESTRATOR] Recording rejection for {ref}..."
    return "[ORCHESTRATOR] Processing command..."


def _action_taken_for_command(command: str, args: list[str]) -> str:
    """Describe the operator action that consumed the previous buttons."""
    if command == "!approve":
        ref = args[0] if args else "<missing-ref>"
        return f"Approve {ref}"
    if command == "!reject":
        ref = args[0] if args else "<missing-ref>"
        return f"Reject {ref}"
    return {
        "!status": "Status",
        "!explain": "Explain",
        "!pause": "Pause",
        "!resume": "Resume",
    }.get(command, command)


def _waiting_on_for_command(command: str) -> str:
    """Describe what the current in-flight message is waiting on."""
    return {
        "!status": "SQLite status read",
        "!explain": "local explanation or deterministic fallback",
        "!pause": "pause flag write",
        "!resume": "resume flag write",
        "!approve": "approval record write",
        "!reject": "rejection record write",
    }.get(command, "command processing")


def _local_validation_summary_mode() -> str:
    """Read the local validation summary mode used by webhook UI state."""
    mode = os.getenv("LOCAL_VALIDATION_SUMMARY", "failures_only").strip().lower()
    if mode not in {"failures_only", "always", "off"}:
        return "failures_only"
    return mode


def _webhook_update_kind(content: str) -> str:
    """Classify orchestrator webhook updates for Discord control state."""
    if content.startswith(MEDIUM_REVIEW_START_PREFIX):
        return "medium_review_start"
    if any(content.startswith(prefix) for prefix in MEDIUM_REVIEW_DONE_PREFIXES):
        return "medium_review_done"
    if (
        _local_validation_summary_mode() != "off"
        and content.startswith("[ORCHESTRATOR")
        and "FAILURE]" in content
        and "Validation failed:" in content
    ):
        return "validation_failure_review_expected"
    return "controls"


def _blocked_during_medium_review_message(command: str, args: list[str]) -> str:
    """Tell operators why commands are temporarily ignored."""
    return (
        "[ORCHESTRATOR] Medium local validation review is still running.\n"
        f"Ignored: {_action_taken_for_command(command, args)}\n"
        "Next: wait for the medium review result or unavailable notice. "
        "Buttons will return when the review finishes."
    )


def _button_followup_message(command: str, response: str) -> str:
    """Return the message that closes a deferred button interaction."""
    if command == "!explain":
        return _text_excerpt_from_string(response, limit=DISCORD_RESPONSE_LIMIT)
    if response == UNKNOWN_COMMAND_MESSAGE:
        return response
    return "Updated task card."


def _model_config_from_env() -> dict[str, str | None]:
    """Collect local model config for operator explanation prompts."""
    return {
        "LOCAL_LLM_BASE_URL": os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1"),
        "LOCAL_LLM_LOW_MODEL": os.getenv("LOCAL_LLM_LOW_MODEL"),
        "LOCAL_LLM_MEDIUM_MODEL": os.getenv("LOCAL_LLM_MEDIUM_MODEL"),
        "LOCAL_LLM_LOW_TIMEOUT_SECONDS": os.getenv("LOCAL_LLM_LOW_TIMEOUT_SECONDS", "30"),
        "LOCAL_LLM_LOW_MAX_TOKENS": os.getenv("LOCAL_LLM_LOW_MAX_TOKENS", "256"),
        "LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS": os.getenv("LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS", "180"),
        "LOCAL_LLM_MEDIUM_MAX_TOKENS": os.getenv("LOCAL_LLM_MEDIUM_MAX_TOKENS", "600"),
    }


def _explain_context(connection: sqlite3.Connection, db_path: str) -> str:
    """Build compact, read-only context for the !explain command."""
    orchestrator_root = Path(db_path).resolve().parent
    project_root = (orchestrator_root / os.getenv("PROJECT_ROOT", "..")).resolve()
    status = _read_status(connection)
    paused_state = _read_paused_state(connection)
    return "\n\n".join(
        [
            "## Current SQLite Status",
            status,
            f"Paused state: {paused_state}",
            "## Latest ACTIVITY Entries",
            _activity_entries(project_root / "ACTIVITY.MD", max_entries=2),
            "## last_prompt.md Excerpt",
            _text_excerpt(orchestrator_root / "last_prompt.md", limit=1200),
        ]
    )


def _deterministic_explain(
    connection: sqlite3.Connection,
    db_path: str,
    reason: str | None = None,
) -> str:
    """Explain the latest action without model assistance."""
    orchestrator_root = Path(db_path).resolve().parent
    project_root = (orchestrator_root / os.getenv("PROJECT_ROOT", "..")).resolve()
    status = _read_status(connection)
    recent_activity = _activity_entries(project_root / "ACTIVITY.MD", max_entries=1)
    reason_text = f"\nLocal model note: {reason}\n" if reason else "\n"
    return (
        "[ORCHESTRATOR] Deterministic explanation\n"
        f"{reason_text}"
        f"What happened:\n{status}\n\n"
        f"Recent activity:\n{recent_activity}\n\n"
        "Next: use the buttons or commands shown below. Use Resume only when the manual task is handled or you intentionally want to re-test."
    )


def _explain_latest_action(connection: sqlite3.Connection, db_path: str) -> str:
    """Return a read-only local-LLM explanation, falling back deterministically."""
    context = _explain_context(connection, db_path)
    prompt_path = MODULE_ROOT / "prompts" / "latest_action_explain.md"
    try:
        response = prompt_runner.run_model_prompt(
            str(prompt_path),
            context,
            ModelTier.LOCAL_LOW,
            _model_config_from_env(),
        )
    except Exception as exc:
        return _deterministic_explain(connection, db_path, reason=f"{type(exc).__name__}: {exc}")

    return response.strip()


def _latest_pending_approval_ref(connection: sqlite3.Connection) -> str | None:
    """Return the newest pending approval ref when the approvals table exists."""
    try:
        row = connection.execute(
            """
            SELECT ref
            FROM approvals
            WHERE ref IS NOT NULL
              AND ref != ''
            GROUP BY ref
            HAVING SUM(
                CASE
                    WHEN decision IS NOT NULL AND decision != '' THEN 1
                    ELSE 0
                END
            ) = 0
            ORDER BY approval_id DESC
            LIMIT 1
            """
        ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    return str(row["ref"])


def _button_actions_for_state(db_path: str) -> list[dict[str, object]]:
    """Build the currently useful Discord button actions from SQLite state."""
    actions: list[dict[str, object]] = [
        {"label": "Status", "command": "!status", "args": []},
        {"label": "Explain", "command": "!explain", "args": []},
    ]
    try:
        with closing(_connect(db_path)) as connection:
            if operator_events.operator_in_flight(connection):
                return []
            paused_state = _read_paused_state(connection)
            if paused_state == "paused":
                actions.append({"label": "Resume", "command": "!resume", "args": []})
            else:
                actions.append({"label": "Pause", "command": "!pause", "args": []})

            pending_ref = _latest_pending_approval_ref(connection)
            if pending_ref:
                actions.append({"label": f"Approve {pending_ref}", "command": "!approve", "args": [pending_ref]})
                actions.append(
                    {
                        "label": f"Reject {pending_ref}",
                        "command": "!reject",
                        "args": [pending_ref, "rejected via Discord button"],
                    }
                )
    except sqlite3.Error:
        actions.append({"label": "Pause", "command": "!pause", "args": []})
    return actions[:5]


def _record_approval(
    connection: sqlite3.Connection,
    ref: str,
    decision: str,
    notes: str | None = None,
) -> None:
    """Insert a decision record into the approvals table."""
    connection.execute(
        """
        INSERT INTO approvals (ref, decision, notes, decided_at)
        VALUES (?, ?, ?, ?)
        """,
        (ref, decision, notes, _now_timestamp()),
    )
    connection.commit()


def _set_paused(connection: sqlite3.Connection, paused: bool) -> None:
    """Persist the orchestrator pause flag in the settings table."""
    connection.execute(
        """
        INSERT OR REPLACE INTO settings (key, value)
        VALUES ('paused', ?)
        """,
        ("1" if paused else "0",),
    )
    connection.commit()


def handle_command(command: str, args: list[str], db_path: str) -> str:
    """Parse and execute a supported Discord command."""
    try:
        with closing(_connect(db_path)) as connection:
            if command == "!status":
                return _task_run_card(db_path)

            if command == "!explain":
                if operator_events.operator_in_flight(connection):
                    return "Explain is unavailable while validation or medium review is running."
                return _explain_latest_action(connection, db_path)

            if command == "!approve":
                if not args:
                    return "Usage: !approve <ref>"
                ref = args[0]
                _record_approval(connection, ref=ref, decision="approved")
                return f"Approved: {ref}"

            if command == "!reject":
                if len(args) < 2:
                    return "Usage: !reject <ref> <notes>"
                ref = args[0]
                notes = " ".join(args[1:]).strip()
                _record_approval(
                    connection,
                    ref=ref,
                    decision="rejected",
                    notes=notes,
                )
                return f"Rejected: {ref} \u2014 {notes}"

            if command == "!pause":
                _set_paused(connection, paused=True)
                operator_events.record_event(
                    db_path,
                    "paused",
                    status="paused",
                    summary="Pause selected. Run loop will wait for Resume.",
                )
                return "Orchestrator paused. Send !resume to continue."

            if command == "!resume":
                _set_paused(connection, paused=False)
                row = _active_task_row(connection)
                operator_events.record_event(
                    db_path,
                    "resume_received",
                    task_id=int(row["task_id"]) if row is not None else None,
                    phase=str(row["phase"]) if row is not None else None,
                    title=str(row["title"]) if row is not None else None,
                    status="resuming",
                    summary="Resume selected. The run loop will continue shortly.",
                )
                return "Orchestrator resumed."
    except sqlite3.Error as exc:
        return f"Database error: {exc}"

    return UNKNOWN_COMMAND_MESSAGE


def _parse_command_line(line: str) -> tuple[str, list[str]] | None:
    """Split a raw line into the command token and its arguments."""
    stripped = line.strip()
    if not stripped or not stripped.startswith("!"):
        return None

    parts = stripped.split()
    command = parts[0].lower()
    command = COMMAND_ALIASES.get(command, command)
    return command, parts[1:]


def _resolve_db_path() -> str:
    """Resolve the database path from the environment or fallback."""
    return (os.getenv("DB_PATH") or DEFAULT_DB_PATH).strip() or DEFAULT_DB_PATH


def _log_stderr(prefix: str, message: str) -> None:
    """Write operational logs to stderr for service visibility."""
    print(f"[DISCORD-LISTENER] {prefix}: {message}", file=sys.stderr)


async def _run_command_async(command: str, args: list[str], db_path: str) -> str:
    """Run the synchronous command path without blocking Discord's event loop."""
    return await asyncio.to_thread(handle_command, command, args, db_path)


def _run_mock_mode(db_path: str) -> None:
    """Run a local stdin loop for testing without a Discord bot token."""
    print(MOCK_MODE_MESSAGE)
    for raw_line in sys.stdin:
        parsed = _parse_command_line(raw_line)
        if parsed is None:
            continue

        command, args = parsed
        _log_stderr("command", raw_line.strip())
        response = handle_command(command, args, db_path)
        _log_stderr("response", response)
        print(response)


def _run_discord_mode(bot_token: str, channel_id: int, db_path: str) -> None:
    """Run the real Discord listener scoped to one command channel."""
    import discord

    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)
    latest_button_message = None
    webhook_loading_message = None
    webhook_typing_task = None
    webhook_action_in_flight = False
    poll_task = None

    def build_action_view() -> discord.ui.View:
        """Create a Discord button view for the current operator actions."""
        view = discord.ui.View(timeout=None)

        for action in _button_actions_for_state(db_path):
            command = str(action["command"])
            args = [str(item) for item in action["args"]]
            label = str(action["label"])[:80]

            class CommandButton(discord.ui.Button):
                def __init__(self, button_label: str, button_command: str, button_args: list[str]) -> None:
                    super().__init__(label=button_label, style=discord.ButtonStyle.secondary)
                    self.button_command = button_command
                    self.button_args = button_args

                async def callback(self, interaction) -> None:
                    await defer_interaction(interaction)
                    if operator_in_flight_now() and self.button_command == "!explain":
                        await send_interaction_followup(
                            interaction,
                            _blocked_during_medium_review_message(self.button_command, self.button_args),
                        )
                        await render_task_card(interaction.channel)
                        return
                    response = await _run_command_async(
                        self.button_command,
                        self.button_args,
                        db_path,
                    )
                    _log_stderr("button", f"{self.button_command} {' '.join(self.button_args)}".strip())
                    _log_stderr("response", response)
                    await send_interaction_followup(
                        interaction,
                        _button_followup_message(self.button_command, response),
                    )
                    await render_task_card(interaction.channel)

            view.add_item(CommandButton(label, command, args))

        return view

    def action_view_or_none():
        """Return buttons only when an operator action is currently allowed."""
        if not _button_actions_for_state(db_path):
            return None
        return build_action_view()

    def build_task_embed() -> discord.Embed:
        """Create the Discord embed for the current task run card."""
        payload = _task_run_card_payload(db_path)
        embed = discord.Embed(
            title=str(payload["title"]),
            color=0xD97706 if operator_in_flight_now() else 0x5865F2,
        )
        embed.add_field(name="Status", value=str(payload["status"]), inline=False)
        embed.add_field(name="Progress", value=str(payload["progress"]), inline=False)
        embed.add_field(name="Current Step", value=str(payload["current"]), inline=False)
        embed.add_field(name="Finding", value=str(payload["finding"]), inline=False)
        embed.add_field(name="Next Action", value=str(payload["next"]), inline=False)
        return embed

    async def defer_interaction(interaction) -> None:
        """Defer a button interaction while preferring ephemeral acknowledgements."""
        try:
            await interaction.response.defer(thinking=True, ephemeral=True)
        except TypeError:
            await interaction.response.defer(thinking=True)

    async def send_interaction_followup(interaction, message: str) -> None:
        """Always close a deferred button interaction with a followup."""
        try:
            await interaction.followup.send(message, ephemeral=True, wait=True)
        except TypeError:
            await interaction.followup.send(message, wait=True)
        except discord.DiscordException:
            await interaction.followup.send(message, wait=True)

    def control_panel_content() -> str:
        return (
            "[ORCHESTRATOR] Operator controls\n"
            "Use the buttons below for the currently safe actions."
        )

    async def clear_latest_buttons(action_taken: str = "", waiting_on: str = "") -> None:
        """Remove action buttons from the previous bot-owned interactive message."""
        nonlocal latest_button_message
        if latest_button_message is None:
            return
        try:
            content = getattr(latest_button_message, "content", "") or ""
            note_parts = []
            if action_taken:
                note_parts.append(f"Action selected: {action_taken}.")
            if waiting_on:
                note_parts.append(f"Waiting on: {waiting_on}.")
            if note_parts:
                content = _text_excerpt_from_string(
                    f"{content}\n\n{' '.join(note_parts)}",
                    limit=DISCORD_RESPONSE_LIMIT,
                )
                await latest_button_message.edit(content=content, view=None)
            else:
                await latest_button_message.edit(view=None)
        except discord.DiscordException as exc:
            _log_stderr("clear-buttons", f"{type(exc).__name__}: {exc}")
        latest_button_message = None

    async def send_response_chunks(channel, response: str, first_message=None, followup=None) -> None:
        """Edit/send one or more Discord messages for a command response."""
        nonlocal latest_button_message
        chunks = _split_discord_messages(response)
        first_chunk_is_final = len(chunks) == 1
        if first_message is not None:
            try:
                await first_message.edit(
                    content=chunks[0],
                    view=build_action_view() if first_chunk_is_final else None,
                )
                if first_chunk_is_final:
                    latest_button_message = first_message
            except discord.DiscordException:
                sent = await channel.send(
                    chunks[0],
                    view=build_action_view() if first_chunk_is_final else None,
                )
                if first_chunk_is_final:
                    latest_button_message = sent
        elif followup is not None:
            latest_button_message = await followup.send(
                chunks[0],
                view=build_action_view() if first_chunk_is_final else None,
                wait=True,
            )
            if not first_chunk_is_final:
                latest_button_message = None
        else:
            sent = await channel.send(
                chunks[0],
                view=build_action_view() if first_chunk_is_final else None,
            )
            if first_chunk_is_final:
                latest_button_message = sent

        for index, chunk in enumerate(chunks[1:], start=1):
            is_final = index == len(chunks) - 1
            sent = await channel.send(
                chunk,
                view=build_action_view() if is_final else None,
            )
            if is_final:
                latest_button_message = sent

    async def send_control_message(channel) -> None:
        """Render the current operator card after webhook-only orchestrator updates."""
        await render_task_card(channel)

    def operator_in_flight_now() -> bool:
        """Read the current in-flight flag from SQLite."""
        try:
            with closing(_connect(db_path)) as connection:
                return operator_events.operator_in_flight(connection)
        except sqlite3.Error:
            return False

    async def start_operator_typing(channel) -> None:
        """Show ongoing work through Discord's typing indicator."""
        nonlocal webhook_typing_task
        if webhook_typing_task is None:
            webhook_typing_task = asyncio.create_task(keep_typing(channel))

    async def stop_operator_typing() -> None:
        """Stop the ongoing typing indicator."""
        nonlocal webhook_typing_task
        if webhook_typing_task is not None:
            webhook_typing_task.cancel()
            with suppress(asyncio.CancelledError):
                await webhook_typing_task
            webhook_typing_task = None

    async def render_task_card(channel) -> None:
        """Create or edit the single evolving task run card."""
        nonlocal latest_button_message
        payload = _task_run_card_payload(db_path)
        content = str(payload["content"])
        embed = build_task_embed()
        in_flight = operator_in_flight_now()
        view = None if in_flight else action_view_or_none()
        if in_flight:
            await start_operator_typing(channel)
        else:
            await stop_operator_typing()

        if latest_button_message is not None:
            try:
                await latest_button_message.edit(content=content, embed=embed, view=view)
                return
            except discord.DiscordException as exc:
                _log_stderr("render-card-edit", f"{type(exc).__name__}: {exc}")
                latest_button_message = None

        message_id = None
        try:
            with closing(_connect(db_path)) as connection:
                message_id = operator_events.get_ui_state(connection, "task_card_message_id")
        except sqlite3.Error:
            message_id = None
        if message_id:
            try:
                fetched = await channel.fetch_message(int(message_id))
                await fetched.edit(content=content, embed=embed, view=view)
                latest_button_message = fetched
                return
            except (discord.DiscordException, ValueError) as exc:
                _log_stderr("render-card-fetch", f"{type(exc).__name__}: {exc}")

        sent = await channel.send(content, embed=embed, view=view)
        latest_button_message = sent
        try:
            with closing(_connect(db_path)) as connection:
                operator_events.set_ui_state(connection, "task_card_message_id", str(sent.id))
        except sqlite3.Error as exc:
            _log_stderr("render-card-state", str(exc))

    async def poll_operator_events(channel) -> None:
        """Render the task card whenever new operator events arrive."""
        while True:
            event_ids: list[int] = []
            try:
                with closing(_connect(db_path)) as connection:
                    rows = operator_events.undelivered_events(connection)
                    event_ids = [int(row["event_id"]) for row in rows]
            except sqlite3.Error as exc:
                _log_stderr("event-poll", str(exc))
            if event_ids:
                await render_task_card(channel)
                try:
                    with closing(_connect(db_path)) as connection:
                        operator_events.mark_delivered(connection, event_ids)
                except sqlite3.Error as exc:
                    _log_stderr("event-delivery", str(exc))
            await asyncio.sleep(float(os.getenv("OPERATOR_EVENT_POLL_SECONDS", "1")))

    async def keep_typing(channel) -> None:
        """Keep Discord's bot typing indicator visible while webhook work runs."""
        while True:
            async with channel.typing():
                await asyncio.sleep(8)

    async def start_webhook_inflight(channel, action_taken: str, waiting_on: str) -> None:
        """Clear controls and show progress while the orchestrator handles webhook work."""
        nonlocal webhook_action_in_flight, webhook_loading_message, webhook_typing_task
        await clear_latest_buttons(action_taken=action_taken, waiting_on=waiting_on)
        webhook_action_in_flight = True
        if webhook_typing_task is not None:
            webhook_typing_task.cancel()
            with suppress(asyncio.CancelledError):
                await webhook_typing_task
        webhook_typing_task = asyncio.create_task(keep_typing(channel))
        message = (
            "[ORCHESTRATOR] Reviewing validation failure with the medium local model...\n"
            "Buttons are hidden until the review result or unavailable notice arrives."
        )
        if webhook_loading_message is None:
            webhook_loading_message = await channel.send(message)
            return
        try:
            await webhook_loading_message.edit(content=message, view=None)
        except discord.DiscordException:
            webhook_loading_message = await channel.send(message)

    async def finish_webhook_inflight(channel) -> None:
        """Stop webhook progress indicators before returning operator controls."""
        nonlocal webhook_action_in_flight, webhook_loading_message, webhook_typing_task
        webhook_action_in_flight = False
        if webhook_typing_task is not None:
            webhook_typing_task.cancel()
            with suppress(asyncio.CancelledError):
                await webhook_typing_task
            webhook_typing_task = None
        if webhook_loading_message is not None:
            try:
                await webhook_loading_message.edit(
                    content="[ORCHESTRATOR] Medium local validation review finished. Controls restored below.",
                    view=None,
                )
            except discord.DiscordException as exc:
                _log_stderr("finish-webhook-inflight", f"{type(exc).__name__}: {exc}")
            webhook_loading_message = None

    async def send_command_response(channel, command: str, args: list[str]) -> None:
        """Show a loading message, then replace it with the command response."""
        if operator_in_flight_now() and command == "!explain":
            await channel.send(_blocked_during_medium_review_message(command, args))
            await render_task_card(channel)
            return
        async with channel.typing():
            response = await _run_command_async(command, args, db_path)
            _log_stderr("response", response)
            if command == "!explain" and "unavailable while validation or medium review is running" not in response:
                await channel.send(_text_excerpt_from_string(response, limit=DISCORD_RESPONSE_LIMIT))
            elif response == UNKNOWN_COMMAND_MESSAGE:
                await channel.send(response)
            await render_task_card(channel)

    @client.event
    async def on_ready() -> None:
        nonlocal poll_task
        _log_stderr("ready", f"connected as {client.user}")
        channel = client.get_channel(channel_id)
        if channel is None:
            channel = await client.fetch_channel(channel_id)
        await render_task_card(channel)
        if poll_task is None:
            poll_task = asyncio.create_task(poll_operator_events(channel))

    @client.event
    async def on_message(message) -> None:
        if message.author == client.user:
            return
        if message.channel.id != channel_id:
            return

        parsed = _parse_command_line(message.content)
        if parsed is None:
            if getattr(message, "webhook_id", None):
                webhook_kind = _webhook_update_kind(message.content or "")
                if webhook_kind == "validation_failure_review_expected":
                    await start_webhook_inflight(
                        message.channel,
                        action_taken="Validation failed",
                        waiting_on="medium local validation review",
                    )
                elif webhook_kind == "medium_review_start":
                    await start_webhook_inflight(
                        message.channel,
                        action_taken="Medium review started",
                        waiting_on="medium local validation review",
                    )
                elif webhook_kind == "medium_review_done":
                    await finish_webhook_inflight(message.channel)
                    await send_control_message(message.channel)
                elif not webhook_action_in_flight:
                    await send_control_message(message.channel)
            return

        command, args = parsed
        _log_stderr("command", message.content.strip())
        await send_command_response(message.channel, command, args)

    client.run(bot_token)


def main() -> None:
    """Start either mock mode or the real Discord listener."""
    _load_local_env()
    db_path = _resolve_db_path()
    bot_token = (os.getenv("DISCORD_BOT_TOKEN") or "").strip()

    if not bot_token:
        _run_mock_mode(db_path)
        return

    channel_id_raw = (os.getenv("DISCORD_COMMAND_CHANNEL_ID") or "").strip()
    if not channel_id_raw:
        raise SystemExit("DISCORD_COMMAND_CHANNEL_ID is required when DISCORD_BOT_TOKEN is set.")

    try:
        channel_id = int(channel_id_raw)
    except ValueError as exc:
        raise SystemExit("DISCORD_COMMAND_CHANNEL_ID must be an integer.") from exc

    _run_discord_mode(bot_token, channel_id, db_path)


if __name__ == "__main__":
    main()
