"""Typed contracts for the deterministic strategy library.

These records are intentionally framework-neutral. Freqtrade adapters,
research jobs, paper execution, and future live execution can consume the
same deterministic outputs without giving strategy code direct exchange,
network, wallet, or model access.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Optional, Protocol, Sequence, Type


class RegimeLabel(str, Enum):
    """High-level market regime used to gate deterministic strategy behavior."""

    BULL = "bull"
    BEAR = "bear"
    RANGE = "range"
    UNKNOWN = "unknown"


class TradeSide(str, Enum):
    """Trade side for entry, sizing, and stop contracts."""

    LONG = "long"
    SHORT = "short"


class EntryDecision(str, Enum):
    """Entry decision emitted by deterministic entry logic."""

    ENTER = "enter"
    HOLD = "hold"


class ExitDecision(str, Enum):
    """Exit decision emitted by deterministic exit logic."""

    EXIT = "exit"
    HOLD = "hold"


def _metadata(metadata: Mapping[str, str]) -> Mapping[str, str]:
    return MappingProxyType(dict(metadata))


def _require_text(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_timestamp(timestamp_ms: int, field_name: str = "timestamp_ms") -> None:
    if not isinstance(timestamp_ms, int):
        raise TypeError(f"{field_name} must be an integer millisecond timestamp")
    if timestamp_ms < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")


def _require_non_negative(value: Decimal, field_name: str) -> None:
    _require_decimal(value, field_name)
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive(value: Decimal, field_name: str) -> None:
    _require_decimal(value, field_name)
    if value <= Decimal("0"):
        raise ValueError(f"{field_name} must be positive")


def _require_ratio(value: Decimal, field_name: str) -> None:
    _require_decimal(value, field_name)
    if value < Decimal("0") or value > Decimal("1"):
        raise ValueError(f"{field_name} must be between 0 and 1")


def _require_enum(value: Enum, enum_type: Type[Enum], field_name: str) -> None:
    if not isinstance(value, enum_type):
        raise TypeError(f"{field_name} must be a {enum_type.__name__}")


@dataclass(frozen=True)
class Candle:
    """One normalized OHLCV candle supplied to deterministic strategy logic."""

    symbol: str
    timeframe: str
    timestamp_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        _require_text(self.timeframe, "timeframe")
        _require_timestamp(self.timestamp_ms)
        for field_name in ("open", "high", "low", "close"):
            _require_positive(getattr(self, field_name), field_name)
        _require_non_negative(self.volume, "volume")
        if self.low > self.high:
            raise ValueError("low must be less than or equal to high")
        if self.open > self.high or self.close > self.high:
            raise ValueError("open and close must be less than or equal to high")
        if self.open < self.low or self.close < self.low:
            raise ValueError("open and close must be greater than or equal to low")


@dataclass(frozen=True)
class MarketSeries:
    """Immutable candle series for one symbol and timeframe."""

    symbol: str
    timeframe: str
    candles: Sequence[Candle]

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        _require_text(self.timeframe, "timeframe")
        if not self.candles:
            raise ValueError("candles must not be empty")
        candles = tuple(self.candles)
        for candle in candles:
            if candle.symbol != self.symbol:
                raise ValueError("all candles must match series symbol")
            if candle.timeframe != self.timeframe:
                raise ValueError("all candles must match series timeframe")
        object.__setattr__(self, "candles", candles)


@dataclass(frozen=True)
class StrategyContext:
    """Replay context shared across deterministic strategy components."""

    run_id: str
    config_hash: str
    as_of_ms: int
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.config_hash, "config_hash")
        _require_timestamp(self.as_of_ms, "as_of_ms")
        object.__setattr__(self, "metadata", _metadata(self.metadata))


@dataclass(frozen=True)
class RegimeAssessment:
    """Deterministic regime output consumed by entries, exits, and snapshots."""

    label: RegimeLabel
    confidence: Decimal
    as_of_ms: int
    reason: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_enum(self.label, RegimeLabel, "label")
        _require_ratio(self.confidence, "confidence")
        _require_timestamp(self.as_of_ms, "as_of_ms")
        _require_text(self.reason, "reason")
        object.__setattr__(self, "metadata", _metadata(self.metadata))


@dataclass(frozen=True)
class EntrySignal:
    """Deterministic entry output. `side` is set only when action is ENTER."""

    symbol: str
    timeframe: str
    action: EntryDecision
    side: Optional[TradeSide]
    strength: Decimal
    timestamp_ms: int
    reason: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        _require_text(self.timeframe, "timeframe")
        _require_enum(self.action, EntryDecision, "action")
        if self.side is not None:
            _require_enum(self.side, TradeSide, "side")
        _require_ratio(self.strength, "strength")
        _require_timestamp(self.timestamp_ms)
        _require_text(self.reason, "reason")
        if self.action is EntryDecision.ENTER and self.side is None:
            raise ValueError("side is required when entry action is ENTER")
        if self.action is EntryDecision.HOLD and self.side is not None:
            raise ValueError("side must be omitted when entry action is HOLD")
        object.__setattr__(self, "metadata", _metadata(self.metadata))


@dataclass(frozen=True)
class ExitSignal:
    """Deterministic exit output. `side` identifies the position side to exit."""

    symbol: str
    timeframe: str
    action: ExitDecision
    side: Optional[TradeSide]
    strength: Decimal
    timestamp_ms: int
    reason: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        _require_text(self.timeframe, "timeframe")
        _require_enum(self.action, ExitDecision, "action")
        if self.side is not None:
            _require_enum(self.side, TradeSide, "side")
        _require_ratio(self.strength, "strength")
        _require_timestamp(self.timestamp_ms)
        _require_text(self.reason, "reason")
        if self.action is ExitDecision.EXIT and self.side is None:
            raise ValueError("side is required when exit action is EXIT")
        if self.action is ExitDecision.HOLD and self.side is not None:
            raise ValueError("side must be omitted when exit action is HOLD")
        object.__setattr__(self, "metadata", _metadata(self.metadata))


@dataclass(frozen=True)
class SizingInput:
    """Inputs for deterministic position-size calculations."""

    symbol: str
    side: TradeSide
    equity: Decimal
    risk_fraction: Decimal
    entry_price: Decimal
    stop_price: Decimal
    max_position_value: Decimal

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        _require_enum(self.side, TradeSide, "side")
        _require_positive(self.equity, "equity")
        _require_ratio(self.risk_fraction, "risk_fraction")
        _require_positive(self.entry_price, "entry_price")
        _require_positive(self.stop_price, "stop_price")
        _require_positive(self.max_position_value, "max_position_value")
        if self.side is TradeSide.LONG and self.stop_price >= self.entry_price:
            raise ValueError("long stop_price must be below entry_price")
        if self.side is TradeSide.SHORT and self.stop_price <= self.entry_price:
            raise ValueError("short stop_price must be above entry_price")


@dataclass(frozen=True)
class PositionSize:
    """Deterministic position-size output before supervisor/risk validation."""

    symbol: str
    side: TradeSide
    quantity: Decimal
    notional: Decimal
    risk_amount: Decimal
    reason: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        _require_enum(self.side, TradeSide, "side")
        _require_non_negative(self.quantity, "quantity")
        _require_non_negative(self.notional, "notional")
        _require_non_negative(self.risk_amount, "risk_amount")
        _require_text(self.reason, "reason")
        object.__setattr__(self, "metadata", _metadata(self.metadata))


@dataclass(frozen=True)
class StopPlan:
    """Deterministic stop and optional target output."""

    symbol: str
    side: TradeSide
    stop_price: Decimal
    take_profit_price: Optional[Decimal]
    trailing_distance: Optional[Decimal]
    reason: str
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        _require_enum(self.side, TradeSide, "side")
        _require_positive(self.stop_price, "stop_price")
        if self.take_profit_price is not None:
            _require_positive(self.take_profit_price, "take_profit_price")
        if self.trailing_distance is not None:
            _require_positive(self.trailing_distance, "trailing_distance")
        _require_text(self.reason, "reason")
        object.__setattr__(self, "metadata", _metadata(self.metadata))


@dataclass(frozen=True)
class StrategySnapshot:
    """Canonical deterministic strategy snapshot for replay and decisioning."""

    symbol: str
    timeframe: str
    timestamp_ms: int
    config_hash: str
    regime: RegimeAssessment
    entry: EntrySignal
    exit: ExitSignal
    sizing_input: Optional[SizingInput]
    position_size: Optional[PositionSize]
    stop_plan: Optional[StopPlan]
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_text(self.symbol, "symbol")
        _require_text(self.timeframe, "timeframe")
        _require_timestamp(self.timestamp_ms)
        _require_text(self.config_hash, "config_hash")
        for named_output in (self.entry, self.exit):
            if named_output.symbol != self.symbol:
                raise ValueError("entry and exit symbols must match snapshot symbol")
            if named_output.timeframe != self.timeframe:
                raise ValueError("entry and exit timeframes must match snapshot timeframe")
        if self.position_size is not None and self.position_size.symbol != self.symbol:
            raise ValueError("position_size symbol must match snapshot symbol")
        if self.stop_plan is not None and self.stop_plan.symbol != self.symbol:
            raise ValueError("stop_plan symbol must match snapshot symbol")
        if self.sizing_input is not None and self.sizing_input.symbol != self.symbol:
            raise ValueError("sizing_input symbol must match snapshot symbol")
        object.__setattr__(self, "metadata", _metadata(self.metadata))


class RegimeClassifier(Protocol):
    """Contract for pure deterministic regime classifiers."""

    def classify(self, series: MarketSeries, context: StrategyContext) -> RegimeAssessment:
        ...


class EntrySignalGenerator(Protocol):
    """Contract for pure deterministic entry signal generators."""

    def generate_entry(
        self,
        series: MarketSeries,
        regime: RegimeAssessment,
        context: StrategyContext,
    ) -> EntrySignal:
        ...


class ExitSignalGenerator(Protocol):
    """Contract for pure deterministic exit signal generators."""

    def generate_exit(
        self,
        series: MarketSeries,
        regime: RegimeAssessment,
        context: StrategyContext,
    ) -> ExitSignal:
        ...


class StopPlanner(Protocol):
    """Contract for pure deterministic stop calculators."""

    def plan_stop(
        self,
        series: MarketSeries,
        entry: EntrySignal,
        context: StrategyContext,
    ) -> Optional[StopPlan]:
        ...


class PositionSizer(Protocol):
    """Contract for pure deterministic position-size calculators."""

    def size(self, sizing_input: SizingInput, context: StrategyContext) -> PositionSize:
        ...


class StrategySnapshotBuilder(Protocol):
    """Contract for building replayable deterministic strategy snapshots."""

    def build_snapshot(
        self,
        series: MarketSeries,
        context: StrategyContext,
    ) -> StrategySnapshot:
        ...


__all__ = [
    "Candle",
    "EntryDecision",
    "EntrySignal",
    "EntrySignalGenerator",
    "ExitDecision",
    "ExitSignal",
    "ExitSignalGenerator",
    "MarketSeries",
    "PositionSize",
    "PositionSizer",
    "RegimeAssessment",
    "RegimeClassifier",
    "RegimeLabel",
    "SizingInput",
    "StopPlan",
    "StopPlanner",
    "StrategyContext",
    "StrategySnapshot",
    "StrategySnapshotBuilder",
    "TradeSide",
]
