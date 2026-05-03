from __future__ import annotations

import re
from pathlib import Path


class TaskNotFound(KeyError):
    """Raised when a requested task cannot be found."""


_TASK_HEADING_RE = re.compile(r"^##\s+(?P<id>\d+)\.\s+(?P<title>.+?)\s*$")
_FIELD_RE = re.compile(r"^-\s+(?P<name>[^:]+):\s*(?P<value>.*)$")
_FILE_RE = re.compile(r"`([^`]+)`")


def _parse_dependencies(value: str) -> list[int]:
    if value.strip().lower() in {"", "none", "n/a"}:
        return []
    return [int(match) for match in re.findall(r"\d+", value)]


def _parse_files(value: str) -> list[str]:
    backticked = _FILE_RE.findall(value)
    if backticked:
        return backticked
    if not value.strip():
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _normalize_task_id(task_id: str) -> int:
    match = re.search(r"\d+", task_id)
    if not match:
        raise TaskNotFound(f"Task {task_id!r} was not found.")
    return int(match.group(0))


def _parse_tasks(queue_path: str) -> list[dict]:
    path = Path(queue_path)
    text = path.read_text(encoding="utf-8")
    tasks: list[dict] = []
    current: dict | None = None

    for line in text.splitlines():
        heading = _TASK_HEADING_RE.match(line)
        if heading:
            if current is not None:
                tasks.append(current)
            current = {
                "id": int(heading.group("id")),
                "title": heading.group("title").strip(),
                "goal": "",
                "files": [],
                "dependencies": [],
                "done_criteria": "",
            }
            continue

        if current is None:
            continue

        field = _FIELD_RE.match(line)
        if not field:
            continue

        name = field.group("name").strip().lower()
        value = field.group("value").strip()
        if name == "goal":
            current["goal"] = value
        elif name == "files likely affected":
            current["files"] = _parse_files(value)
        elif name == "dependencies":
            current["dependencies"] = _parse_dependencies(value)
        elif name == "done criteria":
            current["done_criteria"] = value

    if current is not None:
        tasks.append(current)

    return tasks


def read_task(task_id: str, queue_path: str) -> dict:
    """Read one task from TASK_QUEUE.md."""
    wanted_id = _normalize_task_id(task_id)
    for task in _parse_tasks(queue_path):
        if task["id"] == wanted_id:
            return task
    raise TaskNotFound(f"Task {task_id!r} was not found in {queue_path}.")


def list_tasks(queue_path: str) -> list[dict]:
    """Return all tasks in queue order with summary fields."""
    return [
        {
            "id": task["id"],
            "title": task["title"],
            "dependencies": task["dependencies"],
        }
        for task in _parse_tasks(queue_path)
    ]
