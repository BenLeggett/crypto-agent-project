from __future__ import annotations

from typing import Any


class TaskNotFound(KeyError):
    """Raised when a requested task cannot be found."""


def read_task(task_id: str) -> dict[str, Any]:
    """Return a placeholder task record."""
    _ = task_id
    return {}


def list_tasks() -> list[dict[str, Any]]:
    """Return a placeholder task list."""
    return []
