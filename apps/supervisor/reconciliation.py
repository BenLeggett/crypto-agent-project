"""Deterministic account reconciliation.

This module compares internal state against externally supplied snapshots. It
does not fetch exchange data, read credentials, place orders, or repair state;
later exchange/Freqtrade wiring can feed snapshots into this pure comparator.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence

from libs.strategy.interfaces import TradeSide

ACCOUNT_SNAPSHOT_SCHEMA_VERSION = "account_snapshot.v1"
RECONCILIATION_REPORT_SCHEMA_VERSION = "reconciliation_report.v1"


class ReconciliationStatus(str, Enum):
    """Overall reconciliation status."""

    MATCHED = "matched"
    MISMATCHED = "mismatched"


class ReconciliationSeverity(str, Enum):
    """Mismatch severity for operator handling."""

    WARNING = "warning"
    CRITICAL = "critical"


@dataclass(frozen=True)
class BalanceSnapshot:
    """Balance state for one asset."""

    asset: str
    total: Decimal
    available: Decimal

    def __post_init__(self) -> None:
        _require_text(self.asset, "asset")
        _require_non_negative_decimal(self.total, "total")
        _require_non_negative_decimal(self.available, "available")
        if self.available > self.total:
            raise ValueError("available balance must not exceed total balance")

    def to_record(self) -> dict[str, str]:
        return {
            "asset": self.asset,
            "total": _decimal_text(self.total),
            "available": _decimal_text(self.available),
        }


@dataclass(frozen=True)
class PositionSnapshot:
    """Open position state for reconciliation."""

    symbol: str
    side: TradeSide
    notional: Decimal

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        if not isinstance(self.side, TradeSide):
            raise TypeError("side must be a TradeSide")
        _require_non_negative_decimal(self.notional, "notional")

    @property
    def key(self) -> tuple[str, TradeSide]:
        return (self.symbol, self.side)

    def to_record(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "side": self.side.value,
            "notional": _decimal_text(self.notional),
        }


@dataclass(frozen=True)
class AccountSnapshot:
    """Internal or external account state supplied to reconciliation."""

    snapshot_id: str
    source: str
    run_id: str
    created_at_ms: int
    balances: tuple[BalanceSnapshot, ...] = ()
    positions: tuple[PositionSnapshot, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = ACCOUNT_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, ACCOUNT_SNAPSHOT_SCHEMA_VERSION, "schema_version")
        _require_text(self.snapshot_id, "snapshot_id")
        _require_text(self.source, "source")
        _require_text(self.run_id, "run_id")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        balances = tuple(self.balances)
        positions = tuple(self.positions)
        _require_unique_balance_assets(balances)
        _require_unique_position_keys(positions)
        object.__setattr__(self, "balances", balances)
        object.__setattr__(self, "positions", positions)
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "source": self.source,
            "run_id": self.run_id,
            "created_at_ms": self.created_at_ms,
            "balances": [balance.to_record() for balance in self.balances],
            "positions": [position.to_record() for position in self.positions],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ReconciliationMismatch:
    """One classified mismatch between internal and external snapshots."""

    code: str
    severity: ReconciliationSeverity
    message: str
    entity_type: str
    entity_id: str
    internal_value: Optional[str] = None
    external_value: Optional[str] = None

    def __post_init__(self) -> None:
        _require_text(self.code, "code")
        if not isinstance(self.severity, ReconciliationSeverity):
            raise TypeError("severity must be a ReconciliationSeverity")
        _require_text(self.message, "message")
        _require_text(self.entity_type, "entity_type")
        _require_text(self.entity_id, "entity_id")

    def to_record(self) -> dict[str, Optional[str]]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "internal_value": self.internal_value,
            "external_value": self.external_value,
        }


@dataclass(frozen=True)
class ReconciliationReport:
    """Versioned reconciliation report for logging and later event packets."""

    report_id: str
    run_id: str
    created_at_ms: int
    status: ReconciliationStatus
    mismatches: tuple[ReconciliationMismatch, ...]
    internal_snapshot_id: str
    external_snapshot_id: str
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = RECONCILIATION_REPORT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, RECONCILIATION_REPORT_SCHEMA_VERSION, "schema_version")
        _require_text(self.report_id, "report_id")
        _require_text(self.run_id, "run_id")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        if not isinstance(self.status, ReconciliationStatus):
            raise TypeError("status must be a ReconciliationStatus")
        mismatches = tuple(self.mismatches)
        if self.status is ReconciliationStatus.MATCHED and mismatches:
            raise ValueError("matched reconciliation reports must not contain mismatches")
        if self.status is ReconciliationStatus.MISMATCHED and not mismatches:
            raise ValueError("mismatched reconciliation reports require at least one mismatch")
        _require_text(self.internal_snapshot_id, "internal_snapshot_id")
        _require_text(self.external_snapshot_id, "external_snapshot_id")
        object.__setattr__(self, "mismatches", mismatches)
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "run_id": self.run_id,
            "created_at_ms": self.created_at_ms,
            "status": self.status.value,
            "mismatches": [mismatch.to_record() for mismatch in self.mismatches],
            "internal_snapshot_id": self.internal_snapshot_id,
            "external_snapshot_id": self.external_snapshot_id,
            "metadata": dict(self.metadata),
        }


def reconcile_account_snapshots(
    *,
    report_id: str,
    created_at_ms: int,
    internal: AccountSnapshot,
    external: AccountSnapshot,
    balance_tolerance: Decimal = Decimal("0"),
    position_notional_tolerance: Decimal = Decimal("0"),
) -> ReconciliationReport:
    """Compare internal and external snapshots and classify mismatches."""

    if not isinstance(internal, AccountSnapshot):
        raise TypeError("internal must be an AccountSnapshot")
    if not isinstance(external, AccountSnapshot):
        raise TypeError("external must be an AccountSnapshot")
    _require_non_negative_decimal(balance_tolerance, "balance_tolerance")
    _require_non_negative_decimal(position_notional_tolerance, "position_notional_tolerance")

    mismatches = [
        *_compare_balances(internal.balances, external.balances, balance_tolerance),
        *_compare_positions(internal.positions, external.positions, position_notional_tolerance),
    ]
    return ReconciliationReport(
        report_id=report_id,
        run_id=internal.run_id,
        created_at_ms=created_at_ms,
        status=ReconciliationStatus.MATCHED if not mismatches else ReconciliationStatus.MISMATCHED,
        mismatches=tuple(mismatches),
        internal_snapshot_id=internal.snapshot_id,
        external_snapshot_id=external.snapshot_id,
        metadata={
            "internal_source": internal.source,
            "external_source": external.source,
            "balance_tolerance": _decimal_text(balance_tolerance),
            "position_notional_tolerance": _decimal_text(position_notional_tolerance),
        },
    )


def account_snapshot_from_record(record: Mapping[str, Any]) -> AccountSnapshot:
    """Parse an account snapshot from a JSON-compatible record."""

    return AccountSnapshot(
        snapshot_id=str(_required(record, "snapshot_id")),
        source=str(_required(record, "source")),
        run_id=str(_required(record, "run_id")),
        created_at_ms=int(_required(record, "created_at_ms")),
        balances=tuple(_balance_from_record(item) for item in record.get("balances", [])),
        positions=tuple(_position_from_record(item) for item in record.get("positions", [])),
        metadata=dict(record.get("metadata", {})),
        schema_version=str(record.get("schema_version", ACCOUNT_SNAPSHOT_SCHEMA_VERSION)),
    )


def empty_account_snapshot(*, snapshot_id: str, source: str, run_id: str, created_at_ms: int) -> AccountSnapshot:
    """Build a local empty snapshot for mock-safe command-line smoke checks."""

    return AccountSnapshot(
        snapshot_id=snapshot_id,
        source=source,
        run_id=run_id,
        created_at_ms=created_at_ms,
        balances=(),
        positions=(),
    )


def _compare_balances(
    internal_balances: Sequence[BalanceSnapshot],
    external_balances: Sequence[BalanceSnapshot],
    tolerance: Decimal,
) -> tuple[ReconciliationMismatch, ...]:
    mismatches: list[ReconciliationMismatch] = []
    internal = {balance.asset: balance for balance in internal_balances}
    external = {balance.asset: balance for balance in external_balances}
    for asset in sorted(set(internal) | set(external)):
        internal_balance = internal.get(asset)
        external_balance = external.get(asset)
        if internal_balance is None:
            mismatches.append(
                _mismatch(
                    "unexpected_external_balance",
                    ReconciliationSeverity.WARNING,
                    "external balance is missing from internal state",
                    "balance",
                    asset,
                    None,
                    external_balance.total if external_balance else None,
                )
            )
        elif external_balance is None:
            mismatches.append(
                _mismatch(
                    "missing_external_balance",
                    ReconciliationSeverity.WARNING,
                    "internal balance is missing from external state",
                    "balance",
                    asset,
                    internal_balance.total,
                    None,
                )
            )
        elif abs(internal_balance.total - external_balance.total) > tolerance:
            mismatches.append(
                _mismatch(
                    "balance_total_mismatch",
                    ReconciliationSeverity.WARNING,
                    "internal and external balance totals differ",
                    "balance",
                    asset,
                    internal_balance.total,
                    external_balance.total,
                )
            )
    return tuple(mismatches)


def _compare_positions(
    internal_positions: Sequence[PositionSnapshot],
    external_positions: Sequence[PositionSnapshot],
    tolerance: Decimal,
) -> tuple[ReconciliationMismatch, ...]:
    mismatches: list[ReconciliationMismatch] = []
    internal = {position.key: position for position in internal_positions}
    external = {position.key: position for position in external_positions}
    for key in sorted(set(internal) | set(external), key=lambda item: (item[0], item[1].value)):
        internal_position = internal.get(key)
        external_position = external.get(key)
        entity_id = f"{key[0]}:{key[1].value}"
        if internal_position is None:
            mismatches.append(
                _mismatch(
                    "unexpected_external_position",
                    ReconciliationSeverity.CRITICAL,
                    "external position is missing from internal state",
                    "position",
                    entity_id,
                    None,
                    external_position.notional if external_position else None,
                )
            )
        elif external_position is None:
            mismatches.append(
                _mismatch(
                    "missing_external_position",
                    ReconciliationSeverity.CRITICAL,
                    "internal position is missing from external state",
                    "position",
                    entity_id,
                    internal_position.notional,
                    None,
                )
            )
        elif abs(internal_position.notional - external_position.notional) > tolerance:
            mismatches.append(
                _mismatch(
                    "position_notional_mismatch",
                    ReconciliationSeverity.CRITICAL,
                    "internal and external position notional values differ",
                    "position",
                    entity_id,
                    internal_position.notional,
                    external_position.notional,
                )
            )
    return tuple(mismatches)


def _balance_from_record(record: Mapping[str, Any]) -> BalanceSnapshot:
    return BalanceSnapshot(
        asset=str(_required(record, "asset")),
        total=_decimal_from_record(_required(record, "total"), "total"),
        available=_decimal_from_record(_required(record, "available"), "available"),
    )


def _position_from_record(record: Mapping[str, Any]) -> PositionSnapshot:
    return PositionSnapshot(
        symbol=str(_required(record, "symbol")),
        side=TradeSide(str(_required(record, "side"))),
        notional=_decimal_from_record(_required(record, "notional"), "notional"),
    )


def _mismatch(
    code: str,
    severity: ReconciliationSeverity,
    message: str,
    entity_type: str,
    entity_id: str,
    internal_value: Optional[Decimal],
    external_value: Optional[Decimal],
) -> ReconciliationMismatch:
    return ReconciliationMismatch(
        code=code,
        severity=severity,
        message=message,
        entity_type=entity_type,
        entity_id=entity_id,
        internal_value=None if internal_value is None else _decimal_text(internal_value),
        external_value=None if external_value is None else _decimal_text(external_value),
    )


def _required(record: Mapping[str, Any], field_name: str) -> Any:
    if field_name not in record:
        raise ValueError(f"missing required field: {field_name}")
    return record[field_name]


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


def _require_non_negative_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite() or value < Decimal("0"):
        raise ValueError(f"{field_name} must be a non-negative finite Decimal")


def _decimal_from_record(value: Any, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be a decimal value") from exc
    _require_non_negative_decimal(parsed, field_name)
    return parsed


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


def _string_mapping(value: Mapping[str, str], field_name: str) -> Mapping[str, str]:
    normalized = dict(value)
    for key, item in normalized.items():
        _require_text(key, f"{field_name} key")
        if not isinstance(item, str):
            raise TypeError(f"{field_name} values must be strings")
    return MappingProxyType(normalized)


def _require_unique_balance_assets(balances: Sequence[BalanceSnapshot]) -> None:
    seen: set[str] = set()
    for balance in balances:
        if balance.asset in seen:
            raise ValueError(f"duplicate balance asset: {balance.asset}")
        seen.add(balance.asset)


def _require_unique_position_keys(positions: Sequence[PositionSnapshot]) -> None:
    seen: set[tuple[str, TradeSide]] = set()
    for position in positions:
        if position.key in seen:
            raise ValueError(f"duplicate position: {position.symbol}:{position.side.value}")
        seen.add(position.key)


__all__ = [
    "ACCOUNT_SNAPSHOT_SCHEMA_VERSION",
    "RECONCILIATION_REPORT_SCHEMA_VERSION",
    "AccountSnapshot",
    "BalanceSnapshot",
    "PositionSnapshot",
    "ReconciliationMismatch",
    "ReconciliationReport",
    "ReconciliationSeverity",
    "ReconciliationStatus",
    "account_snapshot_from_record",
    "empty_account_snapshot",
    "reconcile_account_snapshots",
]
