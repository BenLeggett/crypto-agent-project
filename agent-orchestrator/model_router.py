from __future__ import annotations

from enum import Enum


class ModelTier(str, Enum):
    LOCAL_LOW = "local_low"
    LOCAL_MEDIUM = "local_medium"
    CLOUD_HIGH = "cloud_high"
    CLOUD_EXTRA_HIGH = "cloud_extra_high"


TASK_TIER_MAP: dict[str, ModelTier] = {
    "status_summary": ModelTier.LOCAL_LOW,
    "diff_summary": ModelTier.LOCAL_LOW,
    "activity_log_draft": ModelTier.LOCAL_LOW,
    "task_parsing": ModelTier.LOCAL_MEDIUM,
    "codex_prompt_generation": ModelTier.LOCAL_MEDIUM,
    "failed_task_diagnosis": ModelTier.LOCAL_MEDIUM,
    "latest_action_explain": ModelTier.LOCAL_LOW,
    "phase_review": ModelTier.CLOUD_HIGH,
    "architecture_review": ModelTier.CLOUD_EXTRA_HIGH,
    "risk_review": ModelTier.CLOUD_EXTRA_HIGH,
}

RISKY_TASK_TYPES: set[str] = {"architecture_review", "risk_review"}

_TIER_ORDER: dict[ModelTier, int] = {
    ModelTier.LOCAL_LOW: 0,
    ModelTier.LOCAL_MEDIUM: 1,
    ModelTier.CLOUD_HIGH: 2,
    ModelTier.CLOUD_EXTRA_HIGH: 3,
}


def escalate(current: ModelTier) -> ModelTier:
    """Return the next tier up, capped at the highest tier."""
    if current == ModelTier.LOCAL_LOW:
        return ModelTier.LOCAL_MEDIUM
    if current == ModelTier.LOCAL_MEDIUM:
        return ModelTier.CLOUD_HIGH
    if current == ModelTier.CLOUD_HIGH:
        return ModelTier.CLOUD_EXTRA_HIGH
    return ModelTier.CLOUD_EXTRA_HIGH


def route(task_type: str, local_available: bool = True) -> ModelTier:
    """Select the model tier for a task, with fallback for local unavailability."""
    tier = TASK_TIER_MAP.get(task_type, ModelTier.CLOUD_HIGH)

    if not local_available and tier in {ModelTier.LOCAL_LOW, ModelTier.LOCAL_MEDIUM}:
        tier = ModelTier.CLOUD_HIGH

    if task_type in RISKY_TASK_TYPES and _TIER_ORDER[tier] < _TIER_ORDER[ModelTier.CLOUD_HIGH]:
        tier = ModelTier.CLOUD_HIGH

    return tier
