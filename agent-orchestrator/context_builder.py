from __future__ import annotations

from typing import Any


def build_context(task_id: str | None = None) -> dict[str, Any]:
    """Return a placeholder context payload."""
    _ = task_id
    return {}
