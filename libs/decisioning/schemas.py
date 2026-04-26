"""Canonical schemas for decision inputs and trade proposals.

These records are the boundary between deterministic or model-informed signal
generation and later supervisor/risk validation. They are deliberately inert:
they cannot place orders and they contain no exchange credentials or live
execution hooks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Optional, Sequence, Type, Union

from libs.strategy.interfaces import TradeSide


DECISION_INPUT_SCHEMA_VERSION = "decision_input.v1"
MARKET_SNAPSHOT_SCHEMA_VERSION = "market_snapshot.v1"
NO_TRADE_SCHEMA_VERSION = "no_trade_decision.v1"
REJECTION_SCHEMA_VERSION = "proposal_rejection.v1"
TRADE_PROPOSAL_SCHEMA_VERSION = "trade_proposal.v1"


class DecisionSchemaError(ValueError):
    """Raised when a decision schema record is malformed."""


class DecisionMode(str, Enum):
    """Operating mode represented in decision records."""

    OFFLINE = "offline"
    PAPER = "paper"
    FUTURE_LIVE = "future_live"


class SignalSource(str, Enum):
    """Source of the proposal or no-trade decision."""

    DETERMINISTIC = "deterministic"
    MODEL_INFORMED = "model_informed"
    HUMAN_REVIEW = "human_review"


class ProposalAction(str, Enum):
    """Requested trading action before deterministic risk validation."""

    ENTER = "enter"
    EXIT = "exit"


class OrderIntentType(str, Enum):
    """Order-intent type only; actual placement remains in the execution path."""

    MARKET = "market"
    LIMIT = "limit"


class NoTradeReason(str, Enum):
    """Reason a decision cycle produced no proposal."""

    NO_SIGNAL = "no_signal"
    OUT_OF_UNIVERSE = "out_of_universe"
    STALE_DATA = "stale_data"
    INVALID_INPUT = "invalid_input"
    RISK_PRECHECK = "risk_precheck"
    MODEL_UNAVAILABLE = "model_unavailable"
    POLICY_GATED = "policy_gated"


class ProposalRejectionReason(str, Enum):
    """Reasons a malformed or unsafe proposal fails closed."""

    SCHEMA_INVALID = "schema_invalid"
    SYMBOL_NOT_ALLOWED = "symbol_not_allowed"
    STALE_DATA = "stale_data"
    TIMESTAMP_INVALID = "timestamp_invalid"
    SIZE_INVALID = "size_invalid"
    PRICE_INVALID = "price_invalid"
    RATIONALE_MISSING = "rationale_missing"
    MODE_NOT_ALLOWED = "mode_not_allowed"


@dataclass(frozen=True)
class MarketSnapshot:
    """Compact market state supplied to a decision cycle."""

    snapshot_id: str
    symbol: str
    timeframe: str
    timestamp_ms: int
    mark_price: Decimal
    source: str
    bid_price: Optional[Decimal] = None
    ask_price: Optional[Decimal] = None
    features: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = MARKET_SNAPSHOT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, MARKET_SNAPSHOT_SCHEMA_VERSION, "schema_version")
        _require_text(self.snapshot_id, "snapshot_id")
        _require_text(self.symbol, "symbol")
        _require_text(self.timeframe, "timeframe")
        _require_timestamp(self.timestamp_ms, "timestamp_ms")
        _require_positive_decimal(self.mark_price, "mark_price")
        _require_text(self.source, "source")
        if self.bid_price is not None:
            _require_positive_decimal(self.bid_price, "bid_price")
        if self.ask_price is not None:
            _require_positive_decimal(self.ask_price, "ask_price")
        if self.bid_price is not None and self.ask_price is not None and self.bid_price > self.ask_price:
            raise DecisionSchemaError("bid_price must be less than or equal to ask_price")
        object.__setattr__(self, "features", _string_mapping(self.features, "features"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "snapshot_id": self.snapshot_id,
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp_ms": self.timestamp_ms,
            "mark_price": _decimal_text(self.mark_price),
            "source": self.source,
            "bid_price": _optional_decimal_text(self.bid_price),
            "ask_price": _optional_decimal_text(self.ask_price),
            "features": dict(self.features),
        }


@dataclass(frozen=True)
class DecisionInput:
    """Canonical input bundle consumed by a proposal builder."""

    decision_id: str
    run_id: str
    mode: DecisionMode
    market: MarketSnapshot
    config_hash: str
    created_at_ms: int
    allowed_symbols: Sequence[str]
    source: SignalSource
    strategy_snapshot: Optional[Mapping[str, Any]] = None
    max_market_age_ms: int = 300_000
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = DECISION_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, DECISION_INPUT_SCHEMA_VERSION, "schema_version")
        _require_text(self.decision_id, "decision_id")
        _require_text(self.run_id, "run_id")
        _require_enum(self.mode, DecisionMode, "mode")
        if not isinstance(self.market, MarketSnapshot):
            raise TypeError("market must be a MarketSnapshot")
        _require_text(self.config_hash, "config_hash")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        _require_enum(self.source, SignalSource, "source")
        if self.max_market_age_ms <= 0:
            raise DecisionSchemaError("max_market_age_ms must be positive")
        allowed = tuple(self.allowed_symbols)
        if not allowed:
            raise DecisionSchemaError("allowed_symbols must not be empty")
        for symbol in allowed:
            _require_text(symbol, "allowed_symbols item")
        object.__setattr__(self, "allowed_symbols", allowed)
        if self.strategy_snapshot is not None:
            object.__setattr__(self, "strategy_snapshot", MappingProxyType(dict(self.strategy_snapshot)))
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "mode": self.mode.value,
            "market": self.market.to_record(),
            "config_hash": self.config_hash,
            "created_at_ms": self.created_at_ms,
            "allowed_symbols": list(self.allowed_symbols),
            "source": self.source.value,
            "strategy_snapshot": None if self.strategy_snapshot is None else dict(self.strategy_snapshot),
            "max_market_age_ms": self.max_market_age_ms,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TradeProposal:
    """Structured trade proposal that must pass supervisor/risk checks later."""

    proposal_id: str
    decision_id: str
    run_id: str
    mode: DecisionMode
    source: SignalSource
    symbol: str
    action: ProposalAction
    side: TradeSide
    order_type: OrderIntentType
    quantity: Decimal
    notional: Decimal
    entry_price: Decimal
    stop_loss_price: Decimal
    confidence: Decimal
    rationale: str
    created_at_ms: int
    valid_until_ms: int
    take_profit_price: Optional[Decimal] = None
    risk_tags: Sequence[str] = field(default_factory=tuple)
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = TRADE_PROPOSAL_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, TRADE_PROPOSAL_SCHEMA_VERSION, "schema_version")
        _require_text(self.proposal_id, "proposal_id")
        _require_text(self.decision_id, "decision_id")
        _require_text(self.run_id, "run_id")
        _require_enum(self.mode, DecisionMode, "mode")
        _require_enum(self.source, SignalSource, "source")
        _require_text(self.symbol, "symbol")
        _require_enum(self.action, ProposalAction, "action")
        _require_enum(self.side, TradeSide, "side")
        _require_enum(self.order_type, OrderIntentType, "order_type")
        _require_positive_decimal(self.quantity, "quantity")
        _require_positive_decimal(self.notional, "notional")
        _require_positive_decimal(self.entry_price, "entry_price")
        _require_positive_decimal(self.stop_loss_price, "stop_loss_price")
        if self.take_profit_price is not None:
            _require_positive_decimal(self.take_profit_price, "take_profit_price")
        _require_ratio(self.confidence, "confidence")
        _require_text(self.rationale, "rationale")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        _require_timestamp(self.valid_until_ms, "valid_until_ms")
        if self.valid_until_ms <= self.created_at_ms:
            raise DecisionSchemaError("valid_until_ms must be after created_at_ms")
        if self.side is TradeSide.LONG and self.stop_loss_price >= self.entry_price:
            raise DecisionSchemaError("long stop_loss_price must be below entry_price")
        if self.side is TradeSide.SHORT and self.stop_loss_price <= self.entry_price:
            raise DecisionSchemaError("short stop_loss_price must be above entry_price")
        object.__setattr__(self, "risk_tags", _text_tuple(self.risk_tags, "risk_tags"))
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "mode": self.mode.value,
            "source": self.source.value,
            "symbol": self.symbol,
            "action": self.action.value,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": _decimal_text(self.quantity),
            "notional": _decimal_text(self.notional),
            "entry_price": _decimal_text(self.entry_price),
            "stop_loss_price": _decimal_text(self.stop_loss_price),
            "take_profit_price": _optional_decimal_text(self.take_profit_price),
            "confidence": _decimal_text(self.confidence),
            "rationale": self.rationale,
            "created_at_ms": self.created_at_ms,
            "valid_until_ms": self.valid_until_ms,
            "risk_tags": list(self.risk_tags),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class NoTradeDecision:
    """Structured no-trade output for replay and reporting."""

    decision_id: str
    run_id: str
    mode: DecisionMode
    source: SignalSource
    symbol: str
    reason: NoTradeReason
    rationale: str
    confidence: Decimal
    created_at_ms: int
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = NO_TRADE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, NO_TRADE_SCHEMA_VERSION, "schema_version")
        _require_text(self.decision_id, "decision_id")
        _require_text(self.run_id, "run_id")
        _require_enum(self.mode, DecisionMode, "mode")
        _require_enum(self.source, SignalSource, "source")
        _require_text(self.symbol, "symbol")
        _require_enum(self.reason, NoTradeReason, "reason")
        _require_text(self.rationale, "rationale")
        _require_ratio(self.confidence, "confidence")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "mode": self.mode.value,
            "source": self.source.value,
            "symbol": self.symbol,
            "reason": self.reason.value,
            "rationale": self.rationale,
            "confidence": _decimal_text(self.confidence),
            "created_at_ms": self.created_at_ms,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ProposalRejection:
    """Structured fail-closed rejection for malformed proposals."""

    rejection_id: str
    decision_id: str
    reason: ProposalRejectionReason
    message: str
    created_at_ms: int
    proposal_id: Optional[str] = None
    metadata: Mapping[str, str] = field(default_factory=dict)
    schema_version: str = REJECTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_schema(self.schema_version, REJECTION_SCHEMA_VERSION, "schema_version")
        _require_text(self.rejection_id, "rejection_id")
        _require_text(self.decision_id, "decision_id")
        _require_enum(self.reason, ProposalRejectionReason, "reason")
        _require_text(self.message, "message")
        _require_timestamp(self.created_at_ms, "created_at_ms")
        if self.proposal_id is not None:
            _require_text(self.proposal_id, "proposal_id")
        object.__setattr__(self, "metadata", _string_mapping(self.metadata, "metadata"))

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "rejection_id": self.rejection_id,
            "decision_id": self.decision_id,
            "proposal_id": self.proposal_id,
            "reason": self.reason.value,
            "message": self.message,
            "created_at_ms": self.created_at_ms,
            "metadata": dict(self.metadata),
        }


DecisionOutput = Union[TradeProposal, NoTradeDecision]


def _require_schema(value: str, expected: str, field_name: str) -> None:
    if value != expected:
        raise DecisionSchemaError(f"{field_name} must be {expected!r}")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise DecisionSchemaError(f"{field_name} must be a non-empty string")


def _require_timestamp(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be an integer millisecond timestamp")
    if value < 0:
        raise DecisionSchemaError(f"{field_name} must be non-negative")


def _require_enum(value: Enum, enum_type: Type[Enum], field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{field_name} must be a {enum_type.__name__}")


def _require_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if not value.is_finite():
        raise DecisionSchemaError(f"{field_name} must be finite")


def _require_positive_decimal(value: Decimal, field_name: str) -> None:
    _require_decimal(value, field_name)
    if value <= Decimal("0"):
        raise DecisionSchemaError(f"{field_name} must be positive")


def _require_ratio(value: Decimal, field_name: str) -> None:
    _require_decimal(value, field_name)
    if value < Decimal("0") or value > Decimal("1"):
        raise DecisionSchemaError(f"{field_name} must be between 0 and 1")


def _string_mapping(value: Mapping[str, str], field_name: str) -> Mapping[str, str]:
    normalized = dict(value)
    for key, item in normalized.items():
        _require_text(key, f"{field_name} key")
        if not isinstance(item, str):
            raise TypeError(f"{field_name} values must be strings")
    return MappingProxyType(normalized)


def _text_tuple(values: Sequence[str], field_name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    for value in normalized:
        _require_text(value, f"{field_name} item")
    return normalized


def _decimal_text(value: Decimal) -> str:
    _require_decimal(value, "decimal")
    return format(value.normalize(), "f")


def _optional_decimal_text(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return _decimal_text(value)


def decimal_from_record(value: Any, field_name: str) -> Decimal:
    """Parse a Decimal from a serialized record value."""

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DecisionSchemaError(f"{field_name} must be a decimal value") from exc
    _require_decimal(parsed, field_name)
    return parsed


__all__ = [
    "DECISION_INPUT_SCHEMA_VERSION",
    "MARKET_SNAPSHOT_SCHEMA_VERSION",
    "NO_TRADE_SCHEMA_VERSION",
    "REJECTION_SCHEMA_VERSION",
    "TRADE_PROPOSAL_SCHEMA_VERSION",
    "DecisionInput",
    "DecisionMode",
    "DecisionOutput",
    "DecisionSchemaError",
    "MarketSnapshot",
    "NoTradeDecision",
    "NoTradeReason",
    "OrderIntentType",
    "ProposalAction",
    "ProposalRejection",
    "ProposalRejectionReason",
    "SignalSource",
    "TradeProposal",
    "decimal_from_record",
]
