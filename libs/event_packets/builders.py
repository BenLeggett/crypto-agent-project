"""Pure event packet builders.

These helpers build compact packets from already-validated local records. They
do not emit packets automatically, write journals, call exchanges, place orders,
or wire live behavior.
"""

from __future__ import annotations

from typing import Any, Mapping

from libs.event_packets.schemas import EventPacket, EventPacketSeverity, EventPacketType


def build_event_packet(
    *,
    event_type: EventPacketType,
    run_id: str,
    occurred_at_ms: int,
    source: str,
    entity_id: str,
    payload: Mapping[str, Any],
    severity: EventPacketSeverity = EventPacketSeverity.INFO,
    packet_id: str = "",
    metadata: Mapping[str, str] | None = None,
) -> EventPacket:
    """Build one compact event packet with a deterministic default ID."""

    if not isinstance(event_type, EventPacketType):
        raise TypeError("event_type must be an EventPacketType")
    if not isinstance(severity, EventPacketSeverity):
        raise TypeError("severity must be an EventPacketSeverity")
    resolved_packet_id = packet_id or _packet_id(event_type, run_id, entity_id, occurred_at_ms)
    return EventPacket(
        packet_id=resolved_packet_id,
        run_id=run_id,
        event_type=event_type,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=entity_id,
        severity=severity,
        payload=payload,
        metadata={} if metadata is None else metadata,
    )


def build_proposal_packet(
    *,
    run_id: str,
    proposal_id: str,
    occurred_at_ms: int,
    proposal: Mapping[str, Any],
    rejected: bool = False,
    reason: str = "",
    source: str = "decision_engine",
) -> EventPacket:
    """Build a proposal-generated or proposal-rejected packet."""

    event_type = EventPacketType.PROPOSAL_REJECTED if rejected else EventPacketType.PROPOSAL_GENERATED
    severity = EventPacketSeverity.WARNING if rejected else EventPacketSeverity.INFO
    metadata = {"reason": reason} if reason else {}
    return build_event_packet(
        event_type=event_type,
        run_id=run_id,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=proposal_id,
        severity=severity,
        payload=proposal,
        metadata=metadata,
    )


def build_risk_decision_packet(
    *,
    run_id: str,
    decision_id: str,
    occurred_at_ms: int,
    risk_decision: Mapping[str, Any],
    allowed: bool,
    source: str = "supervisor",
) -> EventPacket:
    """Build a risk decision packet, using risk-veto type for denials."""

    return build_event_packet(
        event_type=EventPacketType.RISK_DECISION if allowed else EventPacketType.RISK_VETO,
        run_id=run_id,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=decision_id,
        severity=EventPacketSeverity.INFO if allowed else EventPacketSeverity.WARNING,
        payload=risk_decision,
        metadata={"allowed": str(allowed).lower()},
    )


def build_fill_packet(
    *,
    run_id: str,
    fill_id: str,
    occurred_at_ms: int,
    fill: Mapping[str, Any],
    partial: bool = False,
    source: str = "execution",
) -> EventPacket:
    """Build a fill or partial-fill packet."""

    return build_event_packet(
        event_type=EventPacketType.PARTIAL_FILL if partial else EventPacketType.FILL,
        run_id=run_id,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=fill_id,
        severity=EventPacketSeverity.INFO,
        payload=fill,
        metadata={"partial": str(partial).lower()},
    )


def build_reject_packet(
    *,
    run_id: str,
    reject_id: str,
    occurred_at_ms: int,
    reject: Mapping[str, Any],
    source: str = "execution",
) -> EventPacket:
    """Build an order-rejected packet."""

    return build_event_packet(
        event_type=EventPacketType.ORDER_REJECTED,
        run_id=run_id,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=reject_id,
        severity=EventPacketSeverity.WARNING,
        payload=reject,
    )


def build_restart_packet(
    *,
    run_id: str,
    restart_id: str,
    occurred_at_ms: int,
    restart: Mapping[str, Any],
    source: str = "runtime",
) -> EventPacket:
    """Build a runtime restart packet."""

    return build_event_packet(
        event_type=EventPacketType.RESTART,
        run_id=run_id,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=restart_id,
        severity=EventPacketSeverity.INFO,
        payload=restart,
    )


def build_freeze_packet(
    *,
    run_id: str,
    command_id: str,
    occurred_at_ms: int,
    freeze: Mapping[str, Any],
    kill_switch: bool = False,
    source: str = "supervisor",
) -> EventPacket:
    """Build a risk-freeze or kill-switch packet."""

    return build_event_packet(
        event_type=EventPacketType.KILL_SWITCH_ACTIVATED if kill_switch else EventPacketType.RISK_FREEZE,
        run_id=run_id,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=command_id,
        severity=EventPacketSeverity.CRITICAL if kill_switch else EventPacketSeverity.WARNING,
        payload=freeze,
        metadata={"kill_switch": str(kill_switch).lower()},
    )


def build_flatten_requested_packet(
    *,
    run_id: str,
    request_id: str,
    occurred_at_ms: int,
    request: Mapping[str, Any],
    source: str = "supervisor",
) -> EventPacket:
    """Build a flatten-requested packet without enabling execution."""

    return build_event_packet(
        event_type=EventPacketType.FLATTEN_REQUESTED,
        run_id=run_id,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=request_id,
        severity=EventPacketSeverity.CRITICAL,
        payload=request,
        metadata={"execution_enabled": "false"},
    )


def build_reconciliation_mismatch_packet(
    *,
    run_id: str,
    report_id: str,
    occurred_at_ms: int,
    report: Mapping[str, Any],
    critical: bool = False,
    source: str = "supervisor",
) -> EventPacket:
    """Build a reconciliation-mismatch packet."""

    return build_event_packet(
        event_type=EventPacketType.RECONCILIATION_MISMATCH,
        run_id=run_id,
        occurred_at_ms=occurred_at_ms,
        source=source,
        entity_id=report_id,
        severity=EventPacketSeverity.CRITICAL if critical else EventPacketSeverity.WARNING,
        payload=report,
        metadata={"critical": str(critical).lower()},
    )


def _packet_id(event_type: EventPacketType, run_id: str, entity_id: str, occurred_at_ms: int) -> str:
    return f"{event_type.value}-{run_id}-{entity_id}-{occurred_at_ms}"


__all__ = [
    "build_event_packet",
    "build_fill_packet",
    "build_flatten_requested_packet",
    "build_freeze_packet",
    "build_proposal_packet",
    "build_reconciliation_mismatch_packet",
    "build_reject_packet",
    "build_restart_packet",
    "build_risk_decision_packet",
]
