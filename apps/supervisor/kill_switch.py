"""Kill-switch and flatten workflow records.

This module deliberately stops at deterministic intent generation. Freqtrade or
future live execution wiring must consume these records through a later,
explicitly approved execution path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

from libs.event_packets import EventPacket, build_flatten_requested_packet, build_freeze_packet
from libs.journal import JournalRecord, JournalRecordType
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


@dataclass(frozen=True)
class SupervisorControlAuditArtifacts:
    """Local audit artifacts for supervisor control-plane actions."""

    journal_records: tuple[JournalRecord, ...]
    event_packets: tuple[EventPacket, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "journal_records": [record.to_record() for record in self.journal_records],
            "event_packets": [packet.to_record() for packet in self.event_packets],
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


def control_command_audit_artifacts(
    *,
    command: SupervisorControlCommand,
    state: FreezeState,
    config_hash: str,
    source: str = "supervisor",
) -> SupervisorControlAuditArtifacts:
    """Build local journal and packet artifacts for a control command."""

    if not isinstance(command, SupervisorControlCommand):
        raise TypeError("command must be a SupervisorControlCommand")
    if not isinstance(state, FreezeState):
        raise TypeError("state must be a FreezeState")
    _require_text(config_hash, "config_hash")
    record_payload = {"command": command.to_record(), "state": state.to_record()}
    is_kill_switch = command.action is SupervisorControlAction.ACTIVATE_KILL_SWITCH
    journal = JournalRecord(
        record_id=f"supervisor-control-{command.run_id}-{command.command_id}",
        run_id=command.run_id,
        created_at_ms=command.created_at_ms,
        record_type=JournalRecordType.FREEZE if state.entries_frozen else JournalRecordType.SUPERVISOR_ACTION,
        source=source,
        config_hash=config_hash,
        payload=record_payload,
        metadata={"action": command.action.value},
    )
    packets: tuple[EventPacket, ...] = ()
    if command.action in (SupervisorControlAction.FREEZE_ENTRIES, SupervisorControlAction.ACTIVATE_KILL_SWITCH):
        packets = (
            build_freeze_packet(
                run_id=command.run_id,
                command_id=command.command_id,
                occurred_at_ms=command.created_at_ms,
                freeze=record_payload,
                kill_switch=is_kill_switch,
                source=source,
            ),
        )
    return SupervisorControlAuditArtifacts(journal_records=(journal,), event_packets=packets)


def flatten_workflow_audit_artifacts(
    *,
    request: FlattenWorkflowRequest,
    config_hash: str,
    source: str = "supervisor",
) -> SupervisorControlAuditArtifacts:
    """Build local journal and packet artifacts for a flatten workflow request."""

    if not isinstance(request, FlattenWorkflowRequest):
        raise TypeError("request must be a FlattenWorkflowRequest")
    _require_text(config_hash, "config_hash")
    payload = request.to_record()
    journal = JournalRecord(
        record_id=f"flatten-request-{request.run_id}-{request.request_id}",
        run_id=request.run_id,
        created_at_ms=request.created_at_ms,
        record_type=JournalRecordType.SUPERVISOR_ACTION,
        source=source,
        config_hash=config_hash,
        payload=payload,
        metadata={"execution_enabled": str(request.execution_enabled).lower()},
    )
    packet = build_flatten_requested_packet(
        run_id=request.run_id,
        request_id=request.request_id,
        occurred_at_ms=request.created_at_ms,
        request=payload,
        source=source,
    )
    return SupervisorControlAuditArtifacts(journal_records=(journal,), event_packets=(packet,))


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
    "SupervisorControlAuditArtifacts",
    "activate_kill_switch",
    "build_flatten_workflow_request",
    "control_command_audit_artifacts",
    "flatten_workflow_audit_artifacts",
]
