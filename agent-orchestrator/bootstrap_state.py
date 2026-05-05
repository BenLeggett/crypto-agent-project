from __future__ import annotations

import argparse
import re
import sqlite3
from pathlib import Path

from task_queue_reader import read_task


PHASE_HEADING_RE = re.compile(r"^##\s+Phase\s+(?P<number>\d+)\s+-\s+(?P<name>.+?)\s*$")
PRIMARY_TASK_RE = re.compile(r"^-\s+(?P<task_id>\d+)\.\s+.+$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Bootstrap orchestrator task state.")
    parser.add_argument("--show", action="store_true", help="Show current task state.")
    parser.add_argument("--mark-done", help="Comma-separated task IDs or ranges to mark done, e.g. 1,2,5-7.")
    return parser


def init_tasks_table(db_path: Path) -> None:
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
        connection.commit()
    finally:
        connection.close()


def parse_phase_task_map(phase_map_path: Path) -> list[dict[str, object]]:
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

        if in_primary_tasks:
            task_match = PRIMARY_TASK_RE.match(line)
            if task_match and isinstance(current_phase["tasks"], list):
                current_phase["tasks"].append(int(task_match.group("task_id")))

    return phases


def get_statuses(db_path: Path) -> dict[int, str]:
    connection = sqlite3.connect(db_path)
    try:
        rows = connection.execute("SELECT task_id, status FROM tasks").fetchall()
    finally:
        connection.close()
    return {int(task_id): str(status) for task_id, status in rows if status}


def phase_label(phase: dict[str, object]) -> str:
    return f"Phase {phase['number']} - {phase['name']}"


def print_task_state(phases: list[dict[str, object]], queue_path: Path, db_path: Path) -> None:
    statuses = get_statuses(db_path)
    for phase in phases:
        print(phase_label(phase))
        task_ids = phase.get("tasks", [])
        if not isinstance(task_ids, list) or not task_ids:
            print("  (no tasks)")
            continue
        for task_id in task_ids:
            task = read_task(str(task_id), str(queue_path))
            status = statuses.get(task_id, "pending")
            print(f"  [{status}] {task_id}. {task['title']}")
        print()


def parse_task_ids(raw: str) -> list[int]:
    task_ids: list[int] = []
    for part in raw.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        if "-" in stripped:
            bounds = [item.strip() for item in stripped.split("-", maxsplit=1)]
            if len(bounds) != 2 or not bounds[0] or not bounds[1]:
                raise ValueError(f"Invalid task range: {stripped}")
            start = int(bounds[0])
            end = int(bounds[1])
            if start > end:
                raise ValueError(f"Invalid descending task range: {stripped}")
            task_ids.extend(range(start, end + 1))
            continue
        task_ids.append(int(stripped))
    return task_ids


def find_phase_for_task(phases: list[dict[str, object]], task_id: int) -> str:
    for phase in phases:
        task_ids = phase.get("tasks", [])
        if isinstance(task_ids, list) and task_id in task_ids:
            return phase_label(phase)
    return "Unknown phase"


def seed_tasks(
    phases: list[dict[str, object]],
    queue_path: Path,
    db_path: Path,
) -> None:
    """Ensure every mapped task exists in SQLite with at least a pending status."""
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        for phase in phases:
            task_ids = phase.get("tasks", [])
            if not isinstance(task_ids, list):
                continue
            for task_id in task_ids:
                task = read_task(str(task_id), str(queue_path))
                connection.execute(
                    """
                    INSERT INTO tasks (
                        task_id,
                        phase,
                        title,
                        status,
                        attempts,
                        last_run_id,
                        notes
                    ) VALUES (?, ?, ?, 'pending', 0, NULL, 'Seeded by bootstrap_state.py')
                    ON CONFLICT(task_id) DO UPDATE SET
                        phase = excluded.phase,
                        title = excluded.title
                    """,
                    (
                        task_id,
                        find_phase_for_task(phases, task_id),
                        task["title"],
                    ),
                )
        connection.commit()
    finally:
        connection.close()


def mark_done(task_ids: list[int], phases: list[dict[str, object]], queue_path: Path, db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        for task_id in task_ids:
            task = read_task(str(task_id), str(queue_path))
            connection.execute(
                """
                INSERT INTO tasks (
                    task_id,
                    phase,
                    title,
                    status,
                    attempts,
                    last_run_id,
                    notes
                ) VALUES (?, ?, ?, ?, COALESCE((SELECT attempts FROM tasks WHERE task_id = ?), 0), NULL, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    phase = excluded.phase,
                    title = excluded.title,
                    status = excluded.status,
                    notes = excluded.notes
                """,
                (
                    task_id,
                    find_phase_for_task(phases, task_id),
                    task["title"],
                    "done",
                    task_id,
                    "Set by bootstrap_state.py",
                ),
            )
        connection.commit()
    finally:
        connection.close()


def main() -> int:
    args = build_parser().parse_args()
    if not args.show and not args.mark_done:
        raise SystemExit("Use --show or --mark-done.")

    orchestrator_root = Path(__file__).resolve().parent
    project_root = orchestrator_root.parent
    queue_path = project_root / "docs" / "TASK_QUEUE.md"
    phase_map_path = project_root / "docs" / "PHASE_TASK_MAP.md"
    db_path = orchestrator_root / "state.sqlite"

    init_tasks_table(db_path)
    phases = parse_phase_task_map(phase_map_path)
    seed_tasks(phases, queue_path, db_path)

    if args.mark_done:
        mark_done(parse_task_ids(args.mark_done), phases, queue_path, db_path)

    print_task_state(phases, queue_path, db_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
