"""Deterministic freeze, kill-switch, and flatten-request state.

These records are the risk-governor control plane used by supervisor commands.
They never place orders or call exchanges; a flatten request is only a
structured instruction for a later execution workflow.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional

FREEZE_STATE_SCHEMA_VERSION = "freeze_state.v1"
SUPERVISOR_CONTROL_COMMAND_SCHEMA_VERSION = "supervisor_control_command.v1"


class SupervisorControlAction(str, Enum):
    """Supported deterministic supervisor control actions."""

    FREEZE_ENTRIES = "freeze_entries"
    UNFREEZE_ENTRIES = "unfreeze_entries"
    ACTIVATE_KILL_SWITCH = "activate_kill_switch"
    REQUEST_FLATTEN = "request_flatten"


@dataclass(frozen=True)
class FreezeState:
    """Current deterministic operating controls for entry and flatten gating."""

    entries_frozen: bool = False
    kill_switch_active: bool = False
    flatten_requested: bool = False
    updated_at_ms: int = 0
    reason: str = "initial_state"
    actor: str = "system"
    command_id: Optional[str] = None
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = FREEZE_STATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, FREEZE_STATE_SCHEMA_VERSION, "schema_version")
        _require_timestamp(self.updated_at_ms, "updated_at_ms")
        _require_text(self.reason, "reason")
        _require_text(self.actor, "actor")
        if self.command_id is not None:
            _require_text(self.command_id, "command_id")
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "entries_frozen": self.entries_frozen,
            "kill_switch_active": self.kill_switch_active,
            "flatten_requested": self.flatten_requested,
            "updated_at_ms": self.updated_at_ms,
            "reason": self.reason,
            "actor": self.actor,
            "command_id": self.command_id,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SupervisorControlCommand:
    """Auditable command intent for supervisor control transitions."""

    command_id: str
    run_id: str
    action: SupervisorControlAction
    reason: str
    actor: str
    created_at_ms: int
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = SUPERVISOR_CONTROL_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, SUPERVISOR_CONTROL_COMMAND_SCHEMA_VERSION, "schema_version")
        _require_text(self.command_id, "command_id")
        _require_text(self.run_id, "run_id")
        if not isinstance(self.action, SupervisorControlAction):
            raise TypeError("action must be a SupervisorControlAction")
        _require_text(self.reason, "reason")
        _require_text(self.actor, "actor")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "run_id": self.run_id,
            "action": self.action.value,
            "reason": self.reason,
            "actor": self.actor,
            "created_at_ms": self.created_at_ms,
            "metadata": dict(self.metadata),
        }


def apply_control_command(state: FreezeState, command: SupervisorControlCommand) -> FreezeState:
    """Apply one deterministic supervisor control command."""

    if not isinstance(state, FreezeState):
        raise TypeError("state must be a FreezeState")
    if not isinstance(command, SupervisorControlCommand):
        raise TypeError("command must be a SupervisorControlCommand")

    if command.action is SupervisorControlAction.FREEZE_ENTRIES:
        return _next_state(
            state,
            command,
            entries_frozen=True,
        )
    if command.action is SupervisorControlAction.UNFREEZE_ENTRIES:
        return _next_state(
            state,
            command,
            entries_frozen=False,
        )
    if command.action is SupervisorControlAction.ACTIVATE_KILL_SWITCH:
        return _next_state(
            state,
            command,
            entries_frozen=True,
            kill_switch_active=True,
            flatten_requested=True,
        )
    if command.action is SupervisorControlAction.REQUEST_FLATTEN:
        return _next_state(
            state,
            command,
            entries_frozen=True,
            flatten_requested=True,
        )
    raise ValueError(f"unsupported supervisor control action: {command.action!r}")


def _next_state(
    state: FreezeState,
    command: SupervisorControlCommand,
    *,
    entries_frozen: Optional[bool] = None,
    kill_switch_active: Optional[bool] = None,
    flatten_requested: Optional[bool] = None,
) -> FreezeState:
    return FreezeState(
        entries_frozen=state.entries_frozen if entries_frozen is None else entries_frozen,
        kill_switch_active=state.kill_switch_active if kill_switch_active is None else kill_switch_active,
        flatten_requested=state.flatten_requested if flatten_requested is None else flatten_requested,
        updated_at_ms=command.created_at_ms,
        reason=command.reason,
        actor=command.actor,
        command_id=command.command_id,
        metadata=command.metadata,
    )


def _require_schema(value: str, expected: str, field_name: str) -> None:
    if value != expected:
        raise ValueError(f"{field_name} must be {expected!r}")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_timestamp(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer millisecond timestamp")
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _string_mapping(value: Mapping[str, str], field_name: str) -> Mapping[str, str]:
    normalized = dict(value)
    for key, item in normalized.items():
        _require_text(key, f"{field_name} key")
        if not isinstance(item, str):
            raise TypeError(f"{field_name} values must be strings")
    return MappingProxyType(normalized)


__all__ = [
    "FREEZE_STATE_SCHEMA_VERSION",
    "SUPERVISOR_CONTROL_COMMAND_SCHEMA_VERSION",
    "FreezeState",
    "SupervisorControlAction",
    "SupervisorControlCommand",
    "apply_control_command",
]
