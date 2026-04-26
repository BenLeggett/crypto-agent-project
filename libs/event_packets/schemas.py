"""Compact event packet schemas.

Event packets are small machine-readable records for downstream reporting,
retrieval, and replay. They are inert data objects: they do not call models,
exchanges, notifiers, wallets, or Freqtrade, and they never approve live
execution.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

EVENT_PACKET_SCHEMA_VERSION = "event_packet.v1"


class EventPacketType(str, Enum):
    """Known downstream event categories."""

    SIGNAL_GENERATED = "signal_generated"
    PROPOSAL_GENERATED = "proposal_generated"
    PROPOSAL_REJECTED = "proposal_rejected"
    RISK_DECISION = "risk_decision"
    RISK_VETO = "risk_veto"
    ORDER_SUBMITTED = "order_submitted"
    ORDER_REJECTED = "order_rejected"
    FILL = "fill"
    PARTIAL_FILL = "partial_fill"
    STOP_HIT = "stop_hit"
    DATA_GAP = "data_gap"
    RECONCILIATION_MISMATCH = "reconciliation_mismatch"
    RESTART = "restart"
    RISK_FREEZE = "risk_freeze"
    FLATTEN_REQUESTED = "flatten_requested"
    KILL_SWITCH_ACTIVATED = "kill_switch_activated"
    OPERATOR_UPDATE_SENT = "operator_update_sent"


class EventPacketSeverity(str, Enum):
    """Operational severity for compact event consumers."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class EventPacket:
    """One compact, versioned event packet."""

    packet_id: str
    run_id: str
    event_type: EventPacketType
    occurred_at_ms: int
    source: str
    entity_id: str
    severity: EventPacketSeverity
    payload: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = EVENT_PACKET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, EVENT_PACKET_SCHEMA_VERSION, "schema_version")
        _require_text(self.packet_id, "packet_id")
        _require_text(self.run_id, "run_id")
        if not isinstance(self.event_type, EventPacketType):
            raise TypeError("event_type must be an EventPacketType")
        _require_timestamp(self.occurred_at_ms, "occurred_at_ms")
        _require_text(self.source, "source")
        _require_text(self.entity_id, "entity_id")
        if not isinstance(self.severity, EventPacketSeverity):
            raise TypeError("severity must be an EventPacketSeverity")
        payload = dict(self.payload)
        _require_json_object(payload, "payload")
        object.__setattr__(self, "payload", MappingProxyType(payload))
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "run_id": self.run_id,
            "event_type": self.event_type.value,
            "occurred_at_ms": self.occurred_at_ms,
            "source": self.source,
            "entity_id": self.entity_id,
            "severity": self.severity.value,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }


def event_packet_from_mapping(record: Mapping[str, Any]) -> EventPacket:
    """Parse and validate an event packet from a JSON-compatible mapping."""

    return EventPacket(
        packet_id=str(_required(record, "packet_id")),
        run_id=str(_required(record, "run_id")),
        event_type=EventPacketType(str(_required(record, "event_type"))),
        occurred_at_ms=int(_required(record, "occurred_at_ms")),
        source=str(_required(record, "source")),
        entity_id=str(_required(record, "entity_id")),
        severity=EventPacketSeverity(str(_required(record, "severity"))),
        payload=_mapping(record.get("payload", {}), "payload"),
        metadata=dict(record.get("metadata", {})),
        schema_version=str(record.get("schema_version", EVENT_PACKET_SCHEMA_VERSION)),
    )


def canonical_event_packet_json(packet: EventPacket | Mapping[str, Any]) -> str:
    """Return deterministic compact JSON for packet serialization."""

    payload = packet.to_record() if isinstance(packet, EventPacket) else dict(packet)
    _require_json_object(payload, "packet")
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _required(record: Mapping[str, Any], field_name: str) -> Any:
    if field_name not in record:
        raise ValueError(f"missing required field: {field_name}")
    return record[field_name]


def _mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return value


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


def _require_json_object(value: Mapping[str, Any], field_name: str) -> None:
    try:
        json.dumps(dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    except (TypeError, ValueError) as exc:
        raise TypeError(f"{field_name} must be JSON serializable") from exc


__all__ = [
    "EVENT_PACKET_SCHEMA_VERSION",
    "EventPacket",
    "EventPacketSeverity",
    "EventPacketType",
    "canonical_event_packet_json",
    "event_packet_from_mapping",
]
