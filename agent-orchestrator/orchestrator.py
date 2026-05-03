from __future__ import annotations

import argparse
import inspect
import os
import re
import sqlite3
from datetime import datetime
from pathlib import Path

import activity_logger
import context_builder
import decision_gate
import discord_notifier
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


def build_parser() -> argparse.ArgumentParser:
    """Create the Stage 1 CLI surface."""
    parser = argparse.ArgumentParser(description="Agent orchestrator scaffold.")
    parser.add_argument("--status", action="store_true", help="Show orchestrator status.")
    parser.add_argument("--run-next", action="store_true", help="Run the next task.")
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
        if isinstance(task_ids, list) and any(status_map.get(task_id) != "done" for task_id in task_ids):
            return phase
    return phases[-1]


def find_active_task(phase: dict[str, object], status_map: dict[int, str], queue_path: Path) -> dict | None:
    """Return the first non-done task in the selected phase."""
    task_ids = phase.get("tasks", [])
    if not isinstance(task_ids, list):
        return None
    for task_id in task_ids:
        if status_map.get(task_id) != "done":
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
    files = ", ".join(task["files"]) if task["files"] else "none"
    return "\n".join(
        [
            f"Task {task['id']}: {task['title']}",
            f"Goal: {task['goal']}",
            f"Files likely affected: {files}",
            f"Done criteria: {task['done_criteria']}",
        ]
    )


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


def risky_reasons(task: dict) -> list[str]:
    """Return reasons a task requires a human approval gate."""
    reasons: list[str] = []
    for raw_path in task.get("files", []):
        path = _normalize_repo_path(str(raw_path))
        for forbidden_path in FORBIDDEN_PATHS:
            if path == forbidden_path or path.startswith(forbidden_path):
                reasons.append(f"forbidden path: {path}")
        for prefix in RISKY_PATH_PREFIXES:
            if path == prefix.rstrip("/") or path.startswith(prefix):
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
    if args.phase_review:
        return phase_review(orchestrator_root)
    if args.validate:
        return run_validate()
    print("Orchestrator ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
