"""Kill-switch and flatten workflow records.

This module deliberately stops at deterministic intent generation. Freqtrade or
future live execution wiring must consume these records through a later,
explicitly approved execution path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

from libs.risk import FreezeState, SupervisorControlAction, SupervisorControlCommand, apply_control_command

FLATTEN_WORKFLOW_SCHEMA_VERSION = "flatten_workflow_request.v1"


@dataclass(frozen=True)
class FlattenWorkflowRequest:
    """Machine-readable request to flatten positions through a later executor."""

    request_id: str
    run_id: str
    created_at_ms: int
    reason: str
    actor: str
    state: FreezeState
    execution_enabled: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = FLATTEN_WORKFLOW_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != FLATTEN_WORKFLOW_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {FLATTEN_WORKFLOW_SCHEMA_VERSION!r}")
        _require_text(self.request_id, "request_id")
        _require_text(self.run_id, "run_id")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        _require_text(self.reason, "reason")
        _require_text(self.actor, "actor")
        if not isinstance(self.state, FreezeState):
            raise TypeError("state must be a FreezeState")
        if self.execution_enabled:
            raise ValueError("flatten workflow requests must not enable execution in this phase")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "run_id": self.run_id,
            "created_at_ms": self.created_at_ms,
            "reason": self.reason,
            "actor": self.actor,
            "execution_enabled": self.execution_enabled,
            "state": self.state.to_record(),
            "metadata": dict(self.metadata),
        }


def activate_kill_switch(
    *,
    command_id: str,
    run_id: str,
    reason: str,
    actor: str,
    created_at_ms: int,
    state: Optional[FreezeState] = None,
) -> FreezeState:
    """Activate the kill switch and request flattening without executing it."""

    command = SupervisorControlCommand(
        command_id=command_id,
        run_id=run_id,
        action=SupervisorControlAction.ACTIVATE_KILL_SWITCH,
        reason=reason,
        actor=actor,
        created_at_ms=created_at_ms,
    )
    return apply_control_command(state or FreezeState(), command)


def build_flatten_workflow_request(
    *,
    request_id: str,
    run_id: str,
    reason: str,
    actor: str,
    created_at_ms: int,
    state: Optional[FreezeState] = None,
) -> FlattenWorkflowRequest:
    """Build a deterministic flatten request for later execution wiring."""

    command = SupervisorControlCommand(
        command_id=request_id,
        run_id=run_id,
        action=SupervisorControlAction.REQUEST_FLATTEN,
        reason=reason,
        actor=actor,
        created_at_ms=created_at_ms,
    )
    next_state = apply_control_command(state or FreezeState(), command)
    return FlattenWorkflowRequest(
        request_id=request_id,
        run_id=run_id,
        reason=reason,
        actor=actor,
        created_at_ms=created_at_ms,
        state=next_state,
    )


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_timestamp(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer millisecond timestamp")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


__all__ = [
    "FLATTEN_WORKFLOW_SCHEMA_VERSION",
    "FlattenWorkflowRequest",
    "activate_kill_switch",
    "build_flatten_workflow_request",
]
