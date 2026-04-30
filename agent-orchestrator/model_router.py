from __future__ import annotations

from enum import Enum


class ModelTier(str, Enum):
    LOCAL_LOW = "local_low"
    LOCAL_MEDIUM = "local_medium"
    CLOUD_HIGH = "cloud_high"
    CLOUD_EXTRA_HIGH = "cloud_extra_high"


def route(task_type: str | None = None) -> ModelTier | None:
    """Return a placeholder tier selection for later implementation."""
    _ = task_type
    return None
