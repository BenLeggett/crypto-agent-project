from __future__ import annotations

import argparse
import inspect
import os
import re
import sqlite3
import subprocess
import time
from datetime import datetime
from pathlib import Path

import activity_logger
import context_builder
import decision_gate
import discord_notifier
import operator_events
import prompt_runner
import validator
from validator import FORBIDDEN_PATHS
from model_router import ModelTier
from task_queue_reader import read_task

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for non-venv interpreters
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        _ = (args, kwargs)
        return False


PHASE_HEADING_RE = re.compile(r"^##\s+Phase\s+(?P<number>\d+)\s+-\s+(?P<name>.+?)\s*$")
PRIMARY_TASK_RE = re.compile(r"^-\s+(?P<task_id>\d+)\.\s+.+$")
REQUIRED_CODEX_PROMPT_FIELDS = (
    "TASK_ID:",
    "TASK_TITLE:",
    "OBJECTIVE:",
    "FILES_ALLOWED_TO_MODIFY:",
    "FILES_ALLOWED_TO_INSPECT:",
    "OUT_OF_SCOPE:",
    "ACCEPTANCE_CRITERIA:",
    "VALIDATION_COMMANDS:",
    "STOP_CONDITIONS:",
)
VAGUE_CODEX_PROMPT_PHRASES = (
    "fix the issue",
    "do the right thing",
    "make it better",
    "clean this up",
    "improve the project",
    "handle it",
    "whatever is needed",
)
CODEX_CLARIFICATION_MARKER = "CODEX_NEEDS_CLARIFICATION:"
CODEX_CLARIFICATION_PHRASES = (
    "please clarify",
    "could you clarify",
    "which file",
    "which directory",
    "did you mean",
    "do you want me to",
    "should i",
    "i need more information",
    "ambiguous",
)
TRUE_ENV_VALUES = {"1", "true", "yes", "on"}


def build_parser() -> argparse.ArgumentParser:
    """Create the Stage 1 CLI surface."""
    parser = argparse.ArgumentParser(description="Agent orchestrator scaffold.")
    parser.add_argument("--status", action="store_true", help="Show orchestrator status.")
    parser.add_argument("--run-next", action="store_true", help="Run the next task.")
    parser.add_argument("--run-loop", action="store_true", help="Run the autonomous task loop.")
    parser.add_argument("--phase-review", action="store_true", help="Review the current phase.")
    parser.add_argument("--validate", action="store_true", help="Run validation checks.")
    return parser


def init_state_db(db_path: Path) -> None:
    """Create the Stage 5 sqlite tables if they do not exist yet."""
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
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
            CREATE TABLE IF NOT EXISTS runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
            """
        )
        operator_events.init_operator_tables(connection)
        connection.commit()
    finally:
        connection.close()


def parse_phase_task_map(phase_map_path: Path) -> list[dict[str, object]]:
    """Read phases and their primary task ids from PHASE_TASK_MAP.md."""
    phases: list[dict[str, object]] = []
    current_phase: dict[str, object] | None = None
    in_primary_tasks = False

    for line in phase_map_path.read_text(encoding="utf-8").splitlines():
        heading_match = PHASE_HEADING_RE.match(line)
        if heading_match:
            current_phase = {
                "number": int(heading_match.group("number")),
                "name": heading_match.group("name").strip(),
                "tasks": [],
            }
            phases.append(current_phase)
            in_primary_tasks = False
            continue

        if current_phase is None:
            continue

        if line.strip() == "### Primary tasks":
            in_primary_tasks = True
            continue

        if line.startswith("### "):
            in_primary_tasks = False
            continue

        if not in_primary_tasks:
            continue

        task_match = PRIMARY_TASK_RE.match(line)
        if task_match:
            task_ids = current_phase["tasks"]
            if isinstance(task_ids, list):
                task_ids.append(int(task_match.group("task_id")))

    return phases


def get_task_status_map(db_path: Path) -> dict[int, str]:
    """Return persisted task statuses keyed by task id."""
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT task_id, status FROM tasks").fetchall()
    finally:
        connection.close()
    return {int(task_id): status for task_id, status in rows if status}


def find_current_phase(phases: list[dict[str, object]], status_map: dict[int, str]) -> dict[str, object]:
    """Choose the first phase that is not fully done, defaulting to Phase 1 when empty."""
    if not phases:
        raise ValueError("No phases found in PHASE_TASK_MAP.md.")
    if not status_map:
        return phases[0]

    for phase in phases:
        task_ids = phase.get("tasks", [])
        if isinstance(task_ids, list) and any(
            status_map.get(task_id) not in {"done", "skipped"} for task_id in task_ids
        ):
            return phase
    return phases[-1]


def find_active_task(phase: dict[str, object], status_map: dict[int, str], queue_path: Path) -> dict | None:
    """Return the first non-done task in the selected phase."""
    task_ids = phase.get("tasks", [])
    if not isinstance(task_ids, list):
        return None
    for task_id in task_ids:
        if status_map.get(task_id) not in {"done", "skipped"}:
            return read_task(str(task_id), str(queue_path))
    return None


def read_recent_activity(activity_path: Path, max_entries: int = 3) -> str:
    """Return the last few ACTIVITY.md entries, or a fallback message."""
    if not activity_path.exists():
        return "No activity yet"

    lines = activity_path.read_text(encoding="utf-8").splitlines()
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
        return "No activity yet"
    return "\n\n".join(entries[-max_entries:])


def print_status(orchestrator_root: Path) -> int:
    """Render the read-only orchestrator status summary."""
    project_root = (orchestrator_root / os.getenv("PROJECT_ROOT", "..")).resolve()
    phase_map_path = project_root / "docs" / "PHASE_TASK_MAP.md"
    queue_path = project_root / "docs" / "TASK_QUEUE.md"
    activity_path = project_root / "ACTIVITY.MD"
    db_path = orchestrator_root / "state.sqlite"

    phases = parse_phase_task_map(phase_map_path)
    status_map = get_task_status_map(db_path)
    current_phase = find_current_phase(phases, status_map)
    active_task = find_active_task(current_phase, status_map, queue_path)
    recent_activity = read_recent_activity(activity_path, max_entries=3)

    print("=== ORCHESTRATOR STATUS ===")
    print(f"Phase: Phase {current_phase['number']} - {current_phase['name']}")
    if active_task is None:
        print("Active task: none")
        print("Done criteria: none")
    else:
        print(f"Active task: {active_task['id']} \u2014 {active_task['title']}")
        print(f"Done criteria: {active_task['done_criteria']}")
    print()
    print("Recent activity:")
    print(recent_activity)
    return 0


def format_task_context(task: dict) -> str:
    """Build the task context string injected into the run-next template."""
    files = [str(item) for item in task.get("files", []) if str(item).strip()]
    allowed_files = files or ["none specified"]
    inspect_files = [
        "AGENTS.md",
        "docs/TASK_QUEUE.md",
        "docs/PHASE_TASK_MAP.md",
        "docs/IMPLEMENTATION_PLAN.md",
        *allowed_files,
    ]
    return "\n".join(
        [
            f"TASK_ID: {task['id']}",
            f"TASK_TITLE: {task['title']}",
            "",
            "OBJECTIVE:",
            str(task.get("goal") or "none specified"),
            "",
            "FILES_ALLOWED_TO_MODIFY:",
            *[f"- {path}" for path in allowed_files],
            "",
            "FILES_ALLOWED_TO_INSPECT:",
            *[f"- {path}" for path in dict.fromkeys(inspect_files)],
            "",
            "OUT_OF_SCOPE:",
            "- Do not modify files outside FILES_ALLOWED_TO_MODIFY.",
            "- Do not refactor unrelated code.",
            "- Do not introduce new dependencies unless explicitly listed.",
            "- Do not change environment files, secrets, CI, deployment, or live config.",
            "- Do not make architectural changes unless explicitly requested.",
            "",
            "ACCEPTANCE_CRITERIA:",
            f"- {task.get('done_criteria') or 'none specified'}",
            "",
            "VALIDATION_COMMANDS:",
            "- Run targeted tests for changed modules.",
            "- python -m pytest",
            "",
            "STOP_CONDITIONS:",
            "- If the target file is unclear, stop and explain the ambiguity.",
            "- If required context is missing, stop and explain what is missing.",
            "- If implementation requires modifying files outside FILES_ALLOWED_TO_MODIFY, stop.",
            "- If tests or validation commands are missing and correctness cannot be verified, stop.",
            "- If secrets, credentials, live config, deployment, or risky paths are required, stop.",
            "",
            "## Task Queue Context",
            f"Task {task['id']}: {task['title']}",
            f"Goal: {task.get('goal') or 'none specified'}",
            "Files likely affected: " + (", ".join(files) if files else "none"),
            f"Done criteria: {task.get('done_criteria') or 'none specified'}",
        ]
    )


def lint_codex_prompt_contract(prompt_text: str) -> list[str]:
    """Return prompt-contract issues that must block headless Codex auto mode."""
    issues: list[str] = []
    if not prompt_text.strip():
        return ["prompt is empty"]

    for field in REQUIRED_CODEX_PROMPT_FIELDS:
        if field not in prompt_text:
            issues.append(f"missing required field: {field}")

    lower_prompt = prompt_text.lower()
    for phrase in VAGUE_CODEX_PROMPT_PHRASES:
        if phrase in lower_prompt:
            issues.append(f"blocked vague phrase: {phrase}")

    return issues


def _local_assemble_prompt(template_path: str, task_context: str, output_path: str) -> str:
    """Fallback prompt assembly used until prompt_runner.py is fully implemented."""
    template = Path(template_path).read_text(encoding="utf-8")
    rendered = template.replace("{task_context}", task_context)
    Path(output_path).write_text(rendered, encoding="utf-8")
    return rendered


def ensure_assemble_prompt() -> None:
    """Provide a compatible assemble_prompt implementation if the module is still a stub."""
    try:
        signature = inspect.signature(prompt_runner.assemble_prompt)
    except (TypeError, ValueError):
        prompt_runner.assemble_prompt = _local_assemble_prompt
        return

    parameters = list(signature.parameters)
    if parameters != ["template_path", "task_context", "output_path"]:
        prompt_runner.assemble_prompt = _local_assemble_prompt


def print_prompt_preview(prompt_path: Path, max_lines: int = 20) -> None:
    """Print the first few lines of the rendered prompt."""
    lines = prompt_path.read_text(encoding="utf-8").splitlines()
    for line in lines[:max_lines]:
        print(line)


RISKY_PATH_PREFIXES = ("libs/risk/", "apps/supervisor/", "freqtrade/")


def _normalize_repo_path(path: str) -> str:
    return path.replace("\\", "/").strip("` ")


def _matches_forbidden_path(path: str, forbidden_path: str) -> bool:
    """Return True when a task-declared file overlaps a forbidden path."""
    forbidden = _normalize_repo_path(forbidden_path)
    if forbidden.endswith("/"):
        return path == forbidden.rstrip("/") or path.startswith(forbidden)
    if forbidden == ".env":
        return path == ".env" or path.endswith("/.env")
    return path == forbidden


def _matches_risky_prefix(path: str, prefix: str) -> bool:
    """Return True when a task-declared file is inside a risky project area."""
    normalized_prefix = _normalize_repo_path(prefix).rstrip("/")
    return path == normalized_prefix or path.startswith(f"{normalized_prefix}/")


def risky_reasons(task: dict) -> list[str]:
    """Return reasons a task requires a human approval gate."""
    reasons: list[str] = []
    for raw_path in task.get("files", []):
        path = _normalize_repo_path(str(raw_path))
        for forbidden_path in FORBIDDEN_PATHS:
            if _matches_forbidden_path(path, forbidden_path):
                reasons.append(f"forbidden path: {path}")
        for prefix in RISKY_PATH_PREFIXES:
            if _matches_risky_prefix(path, prefix):
                reasons.append(f"risky path: {path}")
    return reasons


def _log_run_next_activity(
    project_root: Path,
    phase: dict[str, object],
    task: dict,
    outcome: str,
    notes: str,
    model_tier: str = "none",
    model_name: str = "",
) -> None:
    activity_logger.log_activity(
        {
            "run_id": int(datetime.now().strftime("%H%M%S")),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "phase": f"Phase {phase['number']}",
            "task_id": task["id"],
            "action": "Codex prompt generated",
            "model_tier": model_tier,
            "model_name": model_name,
            "outcome": outcome,
            "notes": notes,
        },
        str(project_root / "ACTIVITY.MD"),
    )


def _phase_display_name(phase: dict[str, object]) -> str:
    """Format one phase label consistently for logs and Discord."""
    return f"Phase {phase['number']} - {phase['name']}"


def _phase_from_setting(phases: list[dict[str, object]], setting: str) -> dict[str, object] | None:
    """Resolve a persisted current_phase setting back to a parsed phase object."""
    normalized = setting.strip().lower()
    if not normalized:
        return None
    number_match = re.search(r"\d+", normalized)
    for phase in phases:
        if number_match and str(phase["number"]) == number_match.group(0):
            return phase
        if _phase_display_name(phase).lower() == normalized:
            return phase
    return None


def _select_loop_phase(
    db_path: Path,
    phases: list[dict[str, object]],
    status_map: dict[int, str],
) -> dict[str, object]:
    """Select and persist the phase boundary the run loop must honor."""
    current_phase_setting = _get_setting(db_path, "current_phase", "")
    selected_phase = _phase_from_setting(phases, current_phase_setting)
    if selected_phase is not None:
        return selected_phase

    selected_phase = find_current_phase(phases, status_map)
    _set_setting(db_path, "current_phase", _phase_display_name(selected_phase))
    return selected_phase


def _connect_db(db_path: Path) -> sqlite3.Connection:
    """Open the orchestrator database with the expected journaling mode."""
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def _get_setting(db_path: Path, key: str, default: str = "") -> str:
    """Read a value from the settings table, falling back to the provided default."""
    connection = _connect_db(db_path)
    try:
        row = connection.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
    finally:
        connection.close()
    if row is None or row[0] is None:
        return default
    return str(row[0])


def _set_setting(db_path: Path, key: str, value: str) -> None:
    """Persist one settings value in sqlite."""
    connection = _connect_db(db_path)
    try:
        connection.execute(
            """
            INSERT OR REPLACE INTO settings (key, value)
            VALUES (?, ?)
            """,
            (key, value),
        )
        connection.commit()
    finally:
        connection.close()


def _set_paused(db_path: Path, paused: bool) -> None:
    """Persist the loop pause flag."""
    _set_setting(db_path, "paused", "1" if paused else "0")


def _is_paused(db_path: Path) -> bool:
    """Return True when the loop should wait for a resume command."""
    return _get_setting(db_path, "paused", "0") == "1"


def _task_status(db_path: Path, task_id: int) -> str:
    """Read one task status from sqlite, defaulting to pending for unseeded tasks."""
    connection = _connect_db(db_path)
    try:
        row = connection.execute(
            "SELECT status FROM tasks WHERE task_id = ?",
            (task_id,),
        ).fetchone()
    finally:
        connection.close()
    if row is None or row[0] is None:
        return "pending"
    return str(row[0])


def _mark_task_status(
    db_path: Path,
    task_id: int,
    status: str,
    notes: str = "",
    phase: str = "",
    title: str = "",
) -> None:
    """Update the persisted task status for loop control."""
    connection = _connect_db(db_path)
    try:
        connection.execute(
            """
            INSERT INTO tasks (task_id, phase, title, status, notes)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(task_id) DO UPDATE SET
                phase = COALESCE(NULLIF(excluded.phase, ''), tasks.phase),
                title = COALESCE(NULLIF(excluded.title, ''), tasks.title),
                status = excluded.status,
                notes = excluded.notes
            """,
            (task_id, phase, title, status, notes),
        )
        connection.commit()
    finally:
        connection.close()


def _record_operator_event(
    db_path: Path,
    event_type: str,
    task: dict | None = None,
    phase: str | None = None,
    status: str | None = None,
    summary: str | None = None,
    details: dict[str, object] | None = None,
) -> None:
    """Append a compact event for the Discord task run card."""
    operator_events.record_event(
        db_path,
        event_type,
        task_id=int(task["id"]) if task is not None and task.get("id") is not None else None,
        phase=phase,
        title=str(task["title"]) if task is not None and task.get("title") is not None else None,
        status=status,
        summary=_truncate_for_discord(summary or "", limit=900),
        details=details,
    )


def _create_pending_approval(db_path: Path, gate_type: str, ref: str, notes: str = "") -> None:
    """Insert a pending approval row so the listener and audit trail share one ref."""
    connection = _connect_db(db_path)
    requested_at = datetime.now().isoformat(timespec="seconds")
    try:
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
            (None, gate_type, ref, requested_at, None, None, notes),
        )
        connection.commit()
    finally:
        connection.close()


def _log_loop_activity(
    project_root: Path,
    phase: str,
    task_id: str | int,
    action: str,
    outcome: str,
    notes: str,
    model_tier: str = "none",
    model_name: str = "",
    validation: str = "Not provided",
) -> None:
    """Append one loop event to ACTIVITY.MD."""
    activity_logger.log_activity(
        {
            "run_id": int(datetime.now().strftime("%H%M%S")),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "phase": phase,
            "task_id": task_id,
            "action": action,
            "model_tier": model_tier,
            "model_name": model_name,
            "outcome": outcome,
            "validation": validation,
            "notes": notes,
        },
        str(project_root / "ACTIVITY.MD"),
    )


def _truncate_for_discord(message: str, limit: int = 1800) -> str:
    """Trim long payloads to stay under Discord's message ceiling."""
    text = message.strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 15].rstrip()} ...[truncated]"


def _loop_interval_seconds() -> int:
    """Read the configured run-loop sleep interval."""
    return max(1, int(os.getenv("LOOP_INTERVAL_SECONDS", "30")))


def _codex_timeout_seconds() -> int:
    """Read the maximum time allowed for one Codex subprocess."""
    return max(1, int(os.getenv("CODEX_TIMEOUT_SECONDS", "300")))


def _max_auto_tasks_per_session() -> int:
    """Read the successful auto-task limit for one run-loop session."""
    return max(1, int(os.getenv("MAX_AUTO_TASKS_PER_SESSION", "5")))


def _env_flag(name: str, default: str = "false") -> bool:
    """Return True when an environment flag is set to an affirmative value."""
    return os.getenv(name, default).strip().lower() in TRUE_ENV_VALUES


def _approval_timeout_seconds() -> int:
    """Read the human gate timeout."""
    return max(1, int(os.getenv("ORCHESTRATOR_APPROVAL_TIMEOUT_SECONDS", "3600")))


def _approval_timeout_minutes() -> int:
    """Convert the approval timeout to minutes for Discord messages."""
    timeout_seconds = _approval_timeout_seconds()
    return max(1, timeout_seconds // 60)


def _next_phase(phases: list[dict[str, object]], current_phase: dict[str, object]) -> dict[str, object] | None:
    """Return the next mapped phase after the provided one, if any."""
    for index, phase in enumerate(phases):
        if phase is current_phase:
            if index + 1 < len(phases):
                return phases[index + 1]
            return None
    return None


def _phase_review_result(
    orchestrator_root: Path,
    project_root: Path,
    current_phase: dict[str, object],
) -> str:
    """Run the model-backed review for the current phase."""
    task_ids = current_phase.get("tasks", [])
    if not isinstance(task_ids, list) or not task_ids:
        return "No tasks are mapped to this phase. All tracked tasks may already be complete."

    context_pack = context_builder.build_context(str(task_ids[-1]), str(project_root))
    return prompt_runner.run_model_prompt(
        str(orchestrator_root / "prompts" / "phase_review.md"),
        context_pack,
        ModelTier.CLOUD_HIGH,
        _model_config_from_env(),
    )


def _codex_mode() -> str:
    """Validate and normalize the requested Codex loop mode."""
    mode = os.getenv("CODEX_MODE", "manual").strip().lower()
    if mode not in {"manual", "auto"}:
        raise ValueError(f"Unsupported CODEX_MODE: {mode}")
    return mode


def _local_validation_summary_mode() -> str:
    """Read the advisory local validation summary mode."""
    mode = os.getenv("LOCAL_VALIDATION_SUMMARY", "failures_only").strip().lower()
    if mode not in {"failures_only", "always", "off"}:
        return "failures_only"
    return mode


def _validation_diagnosis_context(
    project_root: Path,
    task: dict,
    validation_result: dict[str, object],
    errors: list[str],
    warnings: list[str],
) -> str:
    """Build compact context for advisory local validation diagnostics."""
    likely_files = ", ".join(str(item) for item in task.get("files", [])) or "none listed"
    failed_commands = [item.split(" failed:", 1)[0] for item in errors if " failed:" in item]
    validation_command = ", ".join(failed_commands) if failed_commands else "validator.validate(project_root)"
    return "\n\n".join(
        [
            "## Active Task",
            f"Task {task['id']}: {task['title']}",
            "## Validation Command",
            validation_command,
            "## Validator Errors",
            _truncate_for_discord("\n".join(f"- {error}" for error in errors), limit=1600)
            if errors
            else "- None",
            "## Validator Warnings",
            "\n".join(f"- {warning}" for warning in warnings) if warnings else "- None",
            "## Relevant File Paths",
            likely_files,
            "## Recent ACTIVITY Tail",
            _truncate_for_discord(
                read_recent_activity(project_root / "ACTIVITY.MD", max_entries=2),
                limit=1200,
            ),
        ]
    )


def _manual_prompt_message(task: dict, prompt_path: Path) -> str:
    """Render the Discord message for manual prompt application."""
    prompt_text = prompt_path.read_text(encoding="utf-8")
    prompt_excerpt = _truncate_for_discord(prompt_text, limit=1400)
    return (
        f"[ORCHESTRATOR] Task {task['id']} prompt ready: {task['title']}\n"
        f"Prompt file: {prompt_path}\n"
        f"Prompt excerpt:\n```text\n{prompt_excerpt}\n```"
    )


def _codex_auto_message(task: dict) -> str:
    """Explain the Codex invocation for auto mode."""
    return (
        f"[ORCHESTRATOR] Running Codex on task {task['id']}: {task['title']}\n"
        f"Implementing: {task['goal']}\n"
        "Mode: auto via `codex exec` with stdin because CODEX_MODE=auto allows "
        "the loop to execute the prepared prompt directly after approval gates pass."
    )


def _codex_last_message_path(project_root: Path) -> Path:
    """Resolve the configured file where Codex writes its final assistant message."""
    raw_path = os.getenv(
        "CODEX_LAST_MESSAGE_PATH",
        "agent-orchestrator/codex_last_message.md",
    ).strip()
    path = Path(raw_path)
    if not path.is_absolute():
        path = project_root / path
    return path


def _build_codex_exec_command(project_root: Path, codex_last_message_path: Path) -> list[str]:
    """Build the Stage 12D Codex CLI command using stdin for the prompt."""
    command = ["codex"]
    if _env_flag("CODEX_ENABLE_SEARCH"):
        command.append("--search")
    command.extend(
        [
            "exec",
            "-C",
            str(project_root),
            "-s",
            "workspace-write",
            "-c",
            'approval_policy="never"',
            "-o",
            str(codex_last_message_path),
        ]
    )
    codex_model = os.getenv("CODEX_MODEL", "").strip()
    if codex_model:
        command.extend(["-m", codex_model])
    # Keep the stdin prompt marker after options so the CLI applies every flag.
    command.append("-")
    return command


def _string_output(value: object) -> str:
    """Normalize subprocess output that may arrive as text, bytes, or None."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _read_codex_last_message(codex_last_message_path: Path) -> tuple[str, str]:
    """Read Codex's final message file, returning a warning if it is absent."""
    if not codex_last_message_path.exists():
        return "", f"Warning: {codex_last_message_path} was not created."
    return codex_last_message_path.read_text(encoding="utf-8", errors="replace"), ""


def _combined_codex_output(stdout: object, stderr: object, last_message: str, warning: str = "") -> str:
    """Join Codex subprocess output and final message for inspection."""
    sections = [
        _string_output(stdout).strip(),
        _string_output(stderr).strip(),
        last_message.strip(),
        warning.strip(),
    ]
    return "\n\n".join(section for section in sections if section)


def _contains_codex_clarification(output_text: str) -> bool:
    """Detect explicit or likely Codex clarification output."""
    if CODEX_CLARIFICATION_MARKER in output_text:
        return True
    lowered = output_text.lower()
    return any(phrase in lowered for phrase in CODEX_CLARIFICATION_PHRASES)


def _prompt_blocked_message(task: dict, issues: list[str]) -> str:
    """Render the Discord/operator message for an underspecified prompt."""
    issue_lines = "\n".join(f"- {issue}" for issue in issues)
    return (
        "[ORCHESTRATOR · PROMPT BLOCKED]\n"
        "Codex was not invoked because the prompt is underspecified.\n\n"
        f"Issues:\n{issue_lines}\n\n"
        f"Reply !clarify {task['id']} <details> or update the task docs."
    )


def _codex_timeout_message(task: dict, timeout_seconds: int) -> str:
    """Render the timeout notification for operators."""
    return (
        "[ORCHESTRATOR · CODEX TIMEOUT]\n"
        f"Task {task['id']}: {task['title']}\n"
        f"Codex exceeded CODEX_TIMEOUT_SECONDS={timeout_seconds}.\n"
        f"Loop paused. Reply !resume to retry or !skip-task {task['id']} to skip."
    )


def _codex_question_message(task: dict, output_text: str) -> str:
    """Render the clarification-needed notification for operators."""
    return (
        "[ORCHESTRATOR · CODEX QUESTION]\n"
        f"Task {task['id']}: {task['title']} needs clarification.\n\n"
        f"{_truncate_for_discord(output_text, limit=1500)}\n\n"
        f"Reply !clarify {task['id']} <your answer> or !skip-task {task['id']}"
    )


def _codex_failure_message(task: dict, output_text: str) -> str:
    """Render a non-zero Codex exit summary."""
    return (
        "[ORCHESTRATOR · CODEX FAILURE]\n"
        f"Task {task['id']}: {task['title']}\n\n"
        f"{_truncate_for_discord(output_text, limit=1500)}"
    )


def _validation_failure_message(task: dict, errors: list[str]) -> str:
    """Build the Discord notification for a failed validation pass."""
    summary = "\n".join(f"- {error}" for error in errors) if errors else "- Unknown validation failure"
    return (
        f"[ORCHESTRATOR · FAILURE] Task {task['id']}: {task['title']}\n"
        f"Validation failed:\n{_truncate_for_discord(summary, limit=1500)}"
    )


def _run_validation_for_task(
    project_root: Path,
    db_path: Path,
    current_phase: dict[str, object],
    active_task: dict,
    codex_mode: str,
    codex_return_code: int = 0,
) -> bool:
    """Validate the workspace and persist the task result."""
    phase_name = _phase_display_name(current_phase)
    _record_operator_event(
        db_path,
        "validating",
        task=active_task,
        phase=phase_name,
        status="validating",
        summary=f"Running deterministic validation for Task {active_task['id']}.",
    )
    validation_result = validator.validate(str(project_root))
    errors = [str(item) for item in validation_result.get("errors", [])]
    warnings = [str(item) for item in validation_result.get("warnings", [])]
    if codex_return_code != 0:
        errors.append(f"codex run exited with return code {codex_return_code}.")
        validation_result["passed"] = False
        validation_result["errors"] = errors

    if not bool(validation_result["passed"]):
        failure_notes = "; ".join(errors + warnings)
        if codex_mode == "auto":
            discord_notifier.notify(_validation_failure_message(active_task, errors))
        _mark_task_status(
            db_path,
            int(active_task["id"]),
            "failed",
            failure_notes or "Validation failed.",
            phase_name,
            str(active_task["title"]),
        )
        _record_operator_event(
            db_path,
            "validation_failed",
            task=active_task,
            phase=phase_name,
            status="failed",
            summary=failure_notes or "Validation failed.",
            details={"errors": errors, "warnings": warnings},
        )
        _set_paused(db_path, True)
        _record_operator_event(
            db_path,
            "paused",
            task=active_task,
            phase=phase_name,
            status="paused",
            summary="Loop paused after failed validation. Repair manually, then resume to re-test.",
        )
        _log_loop_activity(
            project_root,
            phase_name,
            active_task["id"],
            "Validation failed",
            "failed",
            "; ".join(
                item
                for item in [
                    failure_notes or "Validation failed with no error summary.",
                    "Paused immediately; listener will run fast low-model diagnosis asynchronously when available.",
                ]
                if item
            ),
            validation="Failed",
        )
        return False

    _mark_task_status(
        db_path,
        int(active_task["id"]),
        "done",
        f"Completed in run loop with CODEX_MODE={codex_mode}.",
        phase_name,
        str(active_task["title"]),
    )
    _log_loop_activity(
        project_root,
        phase_name,
        active_task["id"],
        "Task completed",
        "passed",
        f"Validation passed after CODEX_MODE={codex_mode}; codex return code={codex_return_code}.",
        validation="Passed",
    )
    _record_operator_event(
        db_path,
        "task_done",
        task=active_task,
        phase=phase_name,
        status="done",
        summary=f"Task {active_task['id']} passed deterministic validation.",
    )
    if codex_mode == "auto":
        discord_notifier.notify(
            f"[ORCHESTRATOR] Task {active_task['id']} complete: {active_task['title']}"
        )
    return True


def _max_iterations_reached(iterations: int, max_iterations: int | None) -> bool:
    """Bound run_loop in tests without changing production behavior."""
    return max_iterations is not None and iterations >= max_iterations


def run_loop(orchestrator_root: Path, max_iterations: int | None = None) -> int:
    """Run the Stage 12b autonomous task loop."""
    project_root = (orchestrator_root / os.getenv("PROJECT_ROOT", "..")).resolve()
    phase_map_path = project_root / "docs" / "PHASE_TASK_MAP.md"
    queue_path = project_root / "docs" / "TASK_QUEUE.md"
    db_path = orchestrator_root / "state.sqlite"
    prompt_template_path = orchestrator_root / "prompts" / "run_next_task.md"
    prompt_output_path = orchestrator_root / "last_prompt.md"

    _log_loop_activity(
        project_root,
        "Run loop",
        "loop",
        "Starting run loop",
        "Loop startup complete.",
        "Run loop initialized and awaiting work.",
    )
    _record_operator_event(
        db_path,
        "run_started",
        summary="Run loop started and is watching for work.",
        status="running",
    )

    iterations = 0
    completed_tasks_this_session = 0
    while True:
        if _max_iterations_reached(iterations, max_iterations):
            return 0

        if _is_paused(db_path):
            time.sleep(_loop_interval_seconds())
            continue
        iterations += 1

        phases = parse_phase_task_map(phase_map_path)
        status_map = get_task_status_map(db_path)
        current_phase_setting = _get_setting(db_path, "current_phase", "")
        if current_phase_setting.strip().lower() == "complete":
            message = "All mapped phases are complete. Run loop stopping."
            _record_operator_event(db_path, "task_done", status="complete", summary=message)
            _log_loop_activity(
                project_root,
                "Run loop",
                "loop",
                "Run loop complete",
                "All mapped phases complete.",
                "current_phase=complete was found in state.sqlite.",
            )
            return 0

        current_phase = _select_loop_phase(db_path, phases, status_map)
        active_task = find_active_task(current_phase, status_map, queue_path)

        if active_task is None:
            task_ids = current_phase.get("tasks", [])
            if not isinstance(task_ids, list) or not task_ids:
                message = "No mapped tasks remain. Run loop stopping."
                _record_operator_event(db_path, "task_done", status="complete", summary=message)
                _log_loop_activity(
                    project_root,
                    "Run loop",
                    "loop",
                    "Run loop complete",
                    "No mapped tasks remain.",
                    "All tracked phases appear complete.",
                )
                return 0

            phase_review_result = _phase_review_result(orchestrator_root, project_root, current_phase)
            phase_ref = f"phase-{current_phase['number']}-exit"
            _create_pending_approval(
                db_path,
                "Phase transition",
                phase_ref,
                f"Awaiting human review for {_phase_display_name(current_phase)}.",
            )
            _record_operator_event(
                db_path,
                "approval_required",
                phase=_phase_display_name(current_phase),
                status="approval_required",
                summary=f"Phase transition approval required: {phase_ref}.",
                details={
                    "ref": phase_ref,
                    "verdict": _truncate_for_discord(phase_review_result, limit=1200),
                    "timeout_minutes": _approval_timeout_minutes(),
                },
            )

            approved = decision_gate.wait_for_approval(
                phase_ref,
                str(db_path),
                _approval_timeout_seconds(),
            )
            decision_gate.record_decision(
                phase_ref,
                "Phase transition",
                "approved" if approved else "rejected",
                "Phase review approved." if approved else "Phase review rejected or timed out.",
                str(db_path),
            )

            if approved:
                next_phase = _next_phase(phases, current_phase)
                _set_setting(
                    db_path,
                    "current_phase",
                    _phase_display_name(next_phase) if next_phase is not None else "complete",
                )
                _log_loop_activity(
                    project_root,
                    _phase_display_name(current_phase),
                    "phase-gate",
                    "Phase review approved",
                    "Phase gate passed.",
                    f"Advanced past {phase_ref}.",
                    model_tier=ModelTier.CLOUD_HIGH.value,
                    model_name=os.getenv("CLOUD_HIGH_MODEL", ""),
                )
                continue

            _set_paused(db_path, True)
            _record_operator_event(
                db_path,
                "paused",
                phase=_phase_display_name(current_phase),
                status="paused",
                summary=f"Phase review for {_phase_display_name(current_phase)} was rejected or timed out. Run loop paused.",
            )
            _log_loop_activity(
                project_root,
                _phase_display_name(current_phase),
                "phase-gate",
                "Phase review blocked",
                "Phase gate rejected or timed out.",
                f"Paused after {phase_ref}.",
                model_tier=ModelTier.CLOUD_HIGH.value,
                model_name=os.getenv("CLOUD_HIGH_MODEL", ""),
            )
            return 0

        codex_mode = _codex_mode()
        active_task_status = _task_status(db_path, int(active_task["id"]))
        is_manual_resume = codex_mode == "manual" and active_task_status in {"in_progress", "failed"}
        codex_return_code = 0
        _set_setting(db_path, "current_task_id", str(active_task["id"]))

        if is_manual_resume:
            _record_operator_event(
                db_path,
                "resume_received",
                task=active_task,
                phase=_phase_display_name(current_phase),
                status="resuming",
                summary=f"Resume selected for Task {active_task['id']}; validation will run next.",
            )
        else:
            reasons = risky_reasons(active_task)
            if reasons:
                risk_ref = f"task-{active_task['id']}-risky"
                verdict = "Human review required: " + "; ".join(reasons)
                _create_pending_approval(db_path, "Risky task", risk_ref, verdict)
                _record_operator_event(
                    db_path,
                    "approval_required",
                    task=active_task,
                    phase=_phase_display_name(current_phase),
                    status="approval_required",
                    summary=f"Risky task approval required: {risk_ref}.",
                    details={
                        "ref": risk_ref,
                        "verdict": verdict,
                        "timeout_minutes": _approval_timeout_minutes(),
                    },
                )

                approved = decision_gate.wait_for_approval(
                    risk_ref,
                    str(db_path),
                    _approval_timeout_seconds(),
                )
                decision_gate.record_decision(
                    risk_ref,
                    "Risky task",
                    "approved" if approved else "rejected",
                    verdict,
                    str(db_path),
                )

                if not approved:
                    _mark_task_status(
                        db_path,
                        int(active_task["id"]),
                        "skipped",
                        f"Skipped after risky gate rejection: {verdict}",
                        _phase_display_name(current_phase),
                        str(active_task["title"]),
                    )
                    _log_loop_activity(
                        project_root,
                        _phase_display_name(current_phase),
                        active_task["id"],
                        "Risky task skipped",
                        "Task skipped after risky gate rejection.",
                        verdict,
                    )
                    _record_operator_event(
                        db_path,
                        "paused",
                        task=active_task,
                        phase=_phase_display_name(current_phase),
                        status="skipped",
                        summary=f"Task {active_task['id']} skipped after risky gate rejection.",
                    )
                    continue

            ensure_assemble_prompt()
            task_context = format_task_context(active_task)
            prompt_runner.assemble_prompt(
                str(prompt_template_path),
                task_context,
                str(prompt_output_path),
            )
            _mark_task_status(
                db_path,
                int(active_task["id"]),
                "in_progress",
                "Prompt assembled for run-loop execution.",
                _phase_display_name(current_phase),
                str(active_task["title"]),
            )

            if codex_mode == "manual":
                _record_operator_event(
                    db_path,
                    "prompt_ready",
                    task=active_task,
                    phase=_phase_display_name(current_phase),
                    status="awaiting_manual",
                    summary="Prompt ready in last_prompt.md. Apply it, then resume to validate.",
                    details={"prompt_path": str(prompt_output_path)},
                )
                _set_paused(db_path, True)
                _record_operator_event(
                    db_path,
                    "paused",
                    task=active_task,
                    phase=_phase_display_name(current_phase),
                    status="paused",
                    summary="Manual mode is paused until the operator resumes.",
                )
                _log_loop_activity(
                    project_root,
                    _phase_display_name(current_phase),
                    active_task["id"],
                    "Prompt assembled",
                    "Awaiting manual application.",
                    "Loop paused in manual mode after writing last_prompt.md.",
                    validation="Pending",
                )
                continue

            prompt_text = prompt_output_path.read_text(encoding="utf-8", errors="replace")
            prompt_issues = lint_codex_prompt_contract(prompt_text)
            if prompt_issues:
                message = _prompt_blocked_message(active_task, prompt_issues)
                _set_paused(db_path, True)
                _set_setting(db_path, "awaiting_clarification_task_id", str(active_task["id"]))
                _mark_task_status(
                    db_path,
                    int(active_task["id"]),
                    "in_progress",
                    "Codex prompt blocked before invocation: " + "; ".join(prompt_issues),
                    _phase_display_name(current_phase),
                    str(active_task["title"]),
                )
                discord_notifier.notify(message)
                _record_operator_event(
                    db_path,
                    "codex_prompt_blocked",
                    task=active_task,
                    phase=_phase_display_name(current_phase),
                    status="paused",
                    summary="Codex prompt blocked before invocation: " + "; ".join(prompt_issues),
                    details={"issues": prompt_issues},
                )
                _log_loop_activity(
                    project_root,
                    _phase_display_name(current_phase),
                    active_task["id"],
                    "Codex prompt blocked",
                    "blocked",
                    "; ".join(prompt_issues),
                    validation="Not run",
                )
                return 0

            codex_last_message_path = _codex_last_message_path(project_root)
            if codex_last_message_path.exists():
                codex_last_message_path.unlink()
            codex_command = _build_codex_exec_command(project_root, codex_last_message_path)
            timeout_seconds = _codex_timeout_seconds()
            discord_notifier.notify(_codex_auto_message(active_task))
            _record_operator_event(
                db_path,
                "validating",
                task=active_task,
                phase=_phase_display_name(current_phase),
                status="codex_running",
                summary=f"Running Codex automatically for Task {active_task['id']}.",
                details={
                    "command": " ".join(codex_command),
                    "timeout_seconds": timeout_seconds,
                },
            )

            try:
                codex_result = subprocess.run(
                    codex_command,
                    input=prompt_text,
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    cwd=project_root,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                output_text = _combined_codex_output(exc.stdout, exc.stderr, "")
                message = _codex_timeout_message(active_task, timeout_seconds)
                _set_paused(db_path, True)
                _set_setting(db_path, "awaiting_review_task_id", str(active_task["id"]))
                discord_notifier.notify(message)
                _record_operator_event(
                    db_path,
                    "codex_timeout",
                    task=active_task,
                    phase=_phase_display_name(current_phase),
                    status="paused",
                    summary=f"Codex timed out after {timeout_seconds} seconds.",
                    details={"output": _truncate_for_discord(output_text, limit=1500)},
                )
                _log_loop_activity(
                    project_root,
                    _phase_display_name(current_phase),
                    active_task["id"],
                    "Codex timeout",
                    "timeout",
                    output_text or f"Codex exceeded CODEX_TIMEOUT_SECONDS={timeout_seconds}.",
                    validation="Not run",
                )
                return 0

            last_message, last_message_warning = _read_codex_last_message(codex_last_message_path)
            output_text = _combined_codex_output(
                codex_result.stdout,
                codex_result.stderr,
                last_message,
                last_message_warning,
            )

            if _contains_codex_clarification(output_text):
                _set_paused(db_path, True)
                _set_setting(db_path, "awaiting_clarification_task_id", str(active_task["id"]))
                message = _codex_question_message(active_task, output_text)
                discord_notifier.notify(message)
                _record_operator_event(
                    db_path,
                    "codex_question",
                    task=active_task,
                    phase=_phase_display_name(current_phase),
                    status="paused",
                    summary="Codex requested clarification or produced ambiguous output.",
                    details={"output": _truncate_for_discord(output_text, limit=1500)},
                )
                _log_loop_activity(
                    project_root,
                    _phase_display_name(current_phase),
                    active_task["id"],
                    "Codex clarification requested",
                    "clarification_required",
                    _truncate_for_discord(output_text, limit=1500),
                    validation="Not run",
                )
                return 0

            codex_return_code = codex_result.returncode
            if codex_return_code != 0:
                _set_paused(db_path, True)
                _set_setting(db_path, "awaiting_review_task_id", str(active_task["id"]))
                message = _codex_failure_message(active_task, output_text)
                discord_notifier.notify(message)
                _record_operator_event(
                    db_path,
                    "codex_failure",
                    task=active_task,
                    phase=_phase_display_name(current_phase),
                    status="paused",
                    summary=f"Codex exited with return code {codex_return_code}.",
                    details={"output": _truncate_for_discord(output_text, limit=1500)},
                )
                _log_loop_activity(
                    project_root,
                    _phase_display_name(current_phase),
                    active_task["id"],
                    "Codex failed",
                    "failed",
                    _truncate_for_discord(output_text, limit=1500),
                    validation="Not run",
                )
                return 0

        validation_passed = _run_validation_for_task(
            project_root,
            db_path,
            current_phase,
            active_task,
            codex_mode,
            codex_return_code,
        )
        if not validation_passed:
            continue
        if codex_mode == "auto":
            completed_tasks_this_session += 1
            max_auto_tasks = _max_auto_tasks_per_session()
            if completed_tasks_this_session >= max_auto_tasks:
                _set_paused(db_path, True)
                message = (
                    "[ORCHESTRATOR]\n"
                    f"Session limit reached ({max_auto_tasks} completed tasks).\n"
                    "Loop paused for human review.\n"
                    "Reply !resume to continue."
                )
                discord_notifier.notify(message)
                _record_operator_event(
                    db_path,
                    "session_limit",
                    task=active_task,
                    phase=_phase_display_name(current_phase),
                    status="paused",
                    summary=f"Session limit reached after {max_auto_tasks} completed auto tasks.",
                )
                _log_loop_activity(
                    project_root,
                    _phase_display_name(current_phase),
                    active_task["id"],
                    "Auto session limit reached",
                    "paused",
                    f"MAX_AUTO_TASKS_PER_SESSION={max_auto_tasks}.",
                    validation="Passed",
                )
                return 0
        if _max_iterations_reached(iterations, max_iterations):
            return 0
        time.sleep(_loop_interval_seconds())


def run_next(orchestrator_root: Path) -> int:
    """Assemble the next-task prompt and write it to last_prompt.md."""
    project_root = (orchestrator_root / os.getenv("PROJECT_ROOT", "..")).resolve()
    phase_map_path = project_root / "docs" / "PHASE_TASK_MAP.md"
    queue_path = project_root / "docs" / "TASK_QUEUE.md"
    db_path = orchestrator_root / "state.sqlite"
    template_path = orchestrator_root / "prompts" / "run_next_task.md"
    output_path = orchestrator_root / "last_prompt.md"

    phases = parse_phase_task_map(phase_map_path)
    status_map = get_task_status_map(db_path)
    current_phase = find_current_phase(phases, status_map)
    active_task = find_active_task(current_phase, status_map, queue_path)
    if active_task is None:
        print("No pending task found for the current phase.")
        return 1

    task_context = format_task_context(active_task)
    reasons = risky_reasons(active_task)
    risk_notes = "No approval gate required."
    if reasons:
        risk_ref = f"task-{active_task['id']}-risk"
        risk_context = context_builder.build_context(str(active_task["id"]), str(project_root))
        risk_result = prompt_runner.run_model_prompt(
            str(orchestrator_root / "prompts" / "risk_review.md"),
            risk_context,
            ModelTier.CLOUD_HIGH,
            _model_config_from_env(),
        )
        approval_message = discord_notifier.format_approval_request(
            "Risky task",
            risk_ref,
            risk_result,
            timeout_minutes=60,
        )
        discord_notifier.notify(approval_message)

        timeout_seconds = int(os.getenv("ORCHESTRATOR_APPROVAL_TIMEOUT_SECONDS", "3600"))
        approved = decision_gate.wait_for_approval(risk_ref, str(db_path), timeout_seconds)
        decision = "approved" if approved else "rejected"
        risk_notes = f"Risk gate {decision}: {', '.join(reasons)}"
        decision_gate.record_decision(risk_ref, "Risky task", decision, risk_notes, str(db_path))
        if not approved:
            _log_run_next_activity(
                project_root,
                current_phase,
                active_task,
                "Risk gate rejected before prompt generation.",
                risk_notes,
                model_tier=ModelTier.CLOUD_HIGH.value,
                model_name=os.getenv("CLOUD_HIGH_MODEL", ""),
            )
            print(f"Risk gate rejected for {risk_ref}")
            return 1

    ensure_assemble_prompt()
    prompt_runner.assemble_prompt(str(template_path), task_context, str(output_path))

    status_message = discord_notifier.format_status(
        f"Phase {current_phase['number']}",
        active_task["id"],
        active_task["title"],
        "none",
        "Codex prompt generated",
        "Review and apply last_prompt.md manually.",
    )
    discord_notifier.notify(status_message)
    _log_run_next_activity(
        project_root,
        current_phase,
        active_task,
        "Prompt written to agent-orchestrator/last_prompt.md",
        risk_notes,
    )

    print("Prompt written to last_prompt.md")
    print_prompt_preview(output_path, max_lines=20)
    return 0


def _model_config_from_env() -> dict[str, str | None]:
    """Collect model config values used by prompt_runner."""
    return {
        "LOCAL_LLM_BASE_URL": os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1"),
        "LOCAL_LLM_LOW_MODEL": os.getenv("LOCAL_LLM_LOW_MODEL"),
        "LOCAL_LLM_MEDIUM_MODEL": os.getenv("LOCAL_LLM_MEDIUM_MODEL"),
        "LOCAL_LLM_LOW_TIMEOUT_SECONDS": os.getenv("LOCAL_LLM_LOW_TIMEOUT_SECONDS", "30"),
        "LOCAL_LLM_LOW_MAX_TOKENS": os.getenv("LOCAL_LLM_LOW_MAX_TOKENS", "256"),
        "LOCAL_LLM_LOW_KEEP_ALIVE": os.getenv("LOCAL_LLM_LOW_KEEP_ALIVE", "30m"),
        "LOCAL_LLM_MEDIUM_WARMUP_TIMEOUT_SECONDS": os.getenv(
            "LOCAL_LLM_MEDIUM_WARMUP_TIMEOUT_SECONDS",
            "120",
        ),
        "LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS": os.getenv("LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS", "180"),
        "LOCAL_LLM_MEDIUM_MAX_TOKENS": os.getenv("LOCAL_LLM_MEDIUM_MAX_TOKENS", "600"),
        "LOCAL_LLM_MEDIUM_KEEP_ALIVE": os.getenv("LOCAL_LLM_MEDIUM_KEEP_ALIVE", "60m"),
        "LOCAL_LLM_UNLOAD_MEDIUM_AFTER_REVIEW": os.getenv(
            "LOCAL_LLM_UNLOAD_MEDIUM_AFTER_REVIEW",
            "false",
        ),
        "OPENAI_API_KEY": os.getenv("OPENAI_API_KEY"),
        "CLOUD_HIGH_MODEL": os.getenv("CLOUD_HIGH_MODEL"),
        "CLOUD_EXTRA_HIGH_MODEL": os.getenv("CLOUD_EXTRA_HIGH_MODEL"),
    }


def phase_review(orchestrator_root: Path) -> int:
    """Run a model-backed phase completion review behind an approval gate."""
    project_root = (orchestrator_root / os.getenv("PROJECT_ROOT", "..")).resolve()
    phase_map_path = project_root / "docs" / "PHASE_TASK_MAP.md"
    db_path = orchestrator_root / "state.sqlite"
    template_path = orchestrator_root / "prompts" / "phase_review.md"

    phases = parse_phase_task_map(phase_map_path)
    status_map = get_task_status_map(db_path)
    current_phase = find_current_phase(phases, status_map)
    task_ids = current_phase.get("tasks", [])
    if not isinstance(task_ids, list) or not task_ids:
        print("No tasks found for the current phase.")
        return 1

    last_task_id = str(task_ids[-1])
    context_pack = context_builder.build_context(last_task_id, str(project_root))
    result = prompt_runner.run_model_prompt(
        str(template_path),
        context_pack,
        ModelTier.CLOUD_HIGH,
        _model_config_from_env(),
    )

    phase_number = current_phase["number"]
    ref = f"phase-{phase_number}-exit"
    approval_message = discord_notifier.format_approval_request(
        "Phase transition",
        ref,
        result,
        timeout_minutes=60,
    )
    discord_notifier.notify(approval_message)

    timeout_seconds = int(os.getenv("ORCHESTRATOR_APPROVAL_TIMEOUT_SECONDS", "3600"))
    approved = decision_gate.wait_for_approval(ref, str(db_path), timeout_seconds)
    decision = "approved" if approved else "rejected"
    notes = "Approved by human." if approved else "Rejected or timed out."
    decision_gate.record_decision(ref, "Phase transition", decision, notes, str(db_path))

    if approved:
        print(f"Phase review approved for {ref}")
        return 0
    print(f"Phase review not approved for {ref}")
    return 1


def _print_validation_section(title: str, items: list[str]) -> None:
    print(f"{title}:")
    if not items:
        print("None")
        return
    for item in items:
        print(item)


def run_validate() -> int:
    """Run validator checks, print the result, and log to ACTIVITY.MD."""
    project_root = str(Path(__file__).parent.parent.resolve())
    result = validator.validate(project_root)
    passed = bool(result["passed"])
    diff_summary = str(result.get("diff_summary") or "No uncommitted changes")
    errors = [str(item) for item in result.get("errors", [])]
    warnings = [str(item) for item in result.get("warnings", [])]

    print("=== VALIDATION RESULT ===")
    print(f"Passed: {passed}")
    print()
    print("Diff summary:")
    print(diff_summary)
    print()
    _print_validation_section("Errors", errors)
    print()
    _print_validation_section("Warnings", warnings)

    activity_logger.log_activity(
        {
            "run_id": int(datetime.now().strftime("%H%M%S")),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "phase": "Orchestrator validation",
            "task_id": "all",
            "action": "Validation run",
            "model_tier": "none",
            "model_name": "",
            "outcome": f"Passed: {passed}",
            "validation": "Passed" if passed else "Failed",
            "notes": f"errors={len(errors)}; warnings={len(warnings)}",
        },
        str(Path(project_root) / "ACTIVITY.MD"),
    )

    return 0 if passed else 1


def main() -> int:
    """Load environment variables, parse CLI flags, and exit cleanly."""
    orchestrator_root = Path(__file__).resolve().parent
    env_path = orchestrator_root / ".env"
    db_path = orchestrator_root / "state.sqlite"
    load_dotenv(env_path)
    init_state_db(db_path)
    args = build_parser().parse_args()
    if args.status:
        return print_status(orchestrator_root)
    if args.run_next:
        return run_next(orchestrator_root)
    if args.run_loop:
        try:
            return run_loop(orchestrator_root)
        except Exception as exc:
            project_root = (orchestrator_root / os.getenv("PROJECT_ROOT", "..")).resolve()
            discord_notifier.notify(f"[ORCHESTRATOR · ERROR] {type(exc).__name__}: {exc}")
            _log_loop_activity(
                project_root,
                "Run loop",
                "loop",
                "Unhandled exception",
                "error",
                f"{type(exc).__name__}: {exc}",
                validation="Failed",
            )
            return 1
    if args.phase_review:
        return phase_review(orchestrator_root)
    if args.validate:
        return run_validate()
    print("Orchestrator ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
