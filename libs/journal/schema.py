"""Structured append-only journal records.

The journal is the local audit boundary for paper mode and later gated live
mode. Records are inert JSON-compatible data: they do not place orders, call
exchanges, invoke models, read secrets, or mutate config.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

JOURNAL_RECORD_SCHEMA_VERSION = "journal_record.v1"


class JournalRecordType(str, Enum):
    """Known audit record categories for staged paper-first operation."""

    MARKET_SNAPSHOT = "market_snapshot"
    PROPOSAL_INPUT = "proposal_input"
    PROPOSAL_OUTPUT = "proposal_output"
    RISK_DECISION = "risk_decision"
    ORDER = "order"
    FILL = "fill"
    FREEZE = "freeze"
    RESTART = "restart"
    MISMATCH = "mismatch"
    SUPERVISOR_ACTION = "supervisor_action"
    OPERATOR_UPDATE = "operator_update"
    ALERT = "alert"
    GENERIC = "generic"


@dataclass(frozen=True)
class JournalRecord:
    """One versioned audit record suitable for JSONL append storage."""

    record_id: str
    run_id: str
    created_at_ms: int
    record_type: JournalRecordType
    source: str
    config_hash: str
    payload: Mapping[str, Any]
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = JOURNAL_RECORD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, JOURNAL_RECORD_SCHEMA_VERSION, "schema_version")
        _require_text(self.record_id, "record_id")
        _require_text(self.run_id, "run_id")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        if not isinstance(self.record_type, JournalRecordType):
            raise TypeError("record_type must be a JournalRecordType")
        _require_text(self.source, "source")
        _require_text(self.config_hash, "config_hash")
        payload = dict(self.payload)
        _require_json_object(payload, "payload")
        object.__setattr__(self, "payload", MappingProxyType(payload))
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "record_id": self.record_id,
            "run_id": self.run_id,
            "created_at_ms": self.created_at_ms,
            "record_type": self.record_type.value,
            "source": self.source,
            "config_hash": self.config_hash,
            "payload": dict(self.payload),
            "metadata": dict(self.metadata),
        }


def journal_record_from_mapping(record: Mapping[str, Any]) -> JournalRecord:
    """Parse and validate a journal record from a JSON-compatible mapping."""

    return JournalRecord(
        record_id=str(_required(record, "record_id")),
        run_id=str(_required(record, "run_id")),
        created_at_ms=int(_required(record, "created_at_ms")),
        record_type=JournalRecordType(str(_required(record, "record_type"))),
        source=str(_required(record, "source")),
        config_hash=str(_required(record, "config_hash")),
        payload=_mapping(_required(record, "payload"), "payload"),
        metadata=dict(record.get("metadata", {})),
        schema_version=str(record.get("schema_version", JOURNAL_RECORD_SCHEMA_VERSION)),
    )


def canonical_journal_json(record: JournalRecord | Mapping[str, Any]) -> str:
    """Return deterministic compact JSON for hashing and JSONL writes."""

    payload = record.to_record() if isinstance(record, JournalRecord) else dict(record)
    _require_json_object(payload, "record")
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
    "JOURNAL_RECORD_SCHEMA_VERSION",
    "JournalRecord",
    "JournalRecordType",
    "canonical_journal_json",
    "journal_record_from_mapping",
]
