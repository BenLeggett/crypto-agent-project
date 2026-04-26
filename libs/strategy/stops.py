"""Pure deterministic stop and target planning."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

from libs.strategy.interfaces import (
    Candle,
    EntryDecision,
    EntrySignal,
    MarketSeries,
    StopPlan,
    StrategyContext,
    TradeSide,
)


@dataclass(frozen=True)
class StopPlanConfig:
    """Bounds for deterministic stop and target placement."""

    lookback_period: int = 5
    stop_buffer: Decimal = Decimal("0.001")
    min_stop_distance: Decimal = Decimal("0.005")
    max_stop_distance: Decimal = Decimal("0.05")
    take_profit_multiple: Decimal = Decimal("2")
    trailing_distance: Optional[Decimal] = None

    def __post_init__(self) -> None:
        if not isinstance(self.lookback_period, int) or self.lookback_period < 1:
            raise ValueError("lookback_period must be a positive integer")
        _require_non_negative_decimal(self.stop_buffer, "stop_buffer")
        _require_positive_decimal(self.min_stop_distance, "min_stop_distance")
        _require_positive_decimal(self.max_stop_distance, "max_stop_distance")
        if self.min_stop_distance > self.max_stop_distance:
            raise ValueError("min_stop_distance must be less than or equal to max_stop_distance")
        _require_positive_decimal(self.take_profit_multiple, "take_profit_multiple")
        if self.trailing_distance is not None:
            _require_positive_decimal(self.trailing_distance, "trailing_distance")


@dataclass(frozen=True)
class StopMetrics:
    """Intermediate deterministic stop metrics for tests and reporting."""

    entry_price: Decimal
    reference_price: Decimal
    raw_stop_distance: Decimal
    bounded_stop_distance: Decimal
    stop_price: Decimal
    take_profit_price: Decimal
    trailing_distance: Optional[Decimal]


class RangeStopPlanner:
    """Plan stops from recent candle range and configured distance bounds."""

    def __init__(self, config: Optional[StopPlanConfig] = None) -> None:
        self.config = config or StopPlanConfig()

    def plan_stop(
        self,
        series: MarketSeries,
        entry: EntrySignal,
        context: StrategyContext,
    ) -> Optional[StopPlan]:
        if entry.action is not EntryDecision.ENTER:
            return None
        if entry.side is None:
            raise ValueError("entry side is required to plan stops")

        metrics = calculate_stop_metrics(series.candles, entry, self.config)
        return StopPlan(
            symbol=series.symbol,
            side=entry.side,
            stop_price=_price(metrics.stop_price),
            take_profit_price=_price(metrics.take_profit_price),
            trailing_distance=_price(metrics.trailing_distance) if metrics.trailing_distance is not None else None,
            reason=(
                "range stop bounded by configured min/max distance: "
                f"raw={_decimal(metrics.raw_stop_distance)}, "
                f"bounded={_decimal(metrics.bounded_stop_distance)}"
            ),
            metadata={
                "run_id": context.run_id,
                "config_hash": context.config_hash,
                "entry_price": _price_text(metrics.entry_price),
                "reference_price": _price_text(metrics.reference_price),
                "raw_stop_distance": _decimal(metrics.raw_stop_distance),
                "bounded_stop_distance": _decimal(metrics.bounded_stop_distance),
                "lookback_period": str(self.config.lookback_period),
            },
        )


def calculate_stop_metrics(
    candles: Sequence[Candle],
    entry: EntrySignal,
    config: Optional[StopPlanConfig] = None,
) -> StopMetrics:
    """Calculate deterministic stop intermediates without side effects."""
    stop_config = config or StopPlanConfig()
    if entry.action is not EntryDecision.ENTER or entry.side is None:
        raise ValueError("stop metrics require an ENTER signal with a side")

    ordered = tuple(candles)
    _validate_candles(ordered, stop_config)
    entry_price = _entry_price(entry, ordered[-1])

    if entry.side is TradeSide.LONG:
        reference_price = min(candle.low for candle in ordered[-stop_config.lookback_period :])
        buffered_reference = reference_price * (Decimal("1") - stop_config.stop_buffer)
        raw_distance = (entry_price - buffered_reference) / entry_price
        bounded_distance = _clamp(raw_distance, stop_config.min_stop_distance, stop_config.max_stop_distance)
        stop_price = entry_price * (Decimal("1") - bounded_distance)
        take_profit_price = entry_price * (Decimal("1") + bounded_distance * stop_config.take_profit_multiple)
    else:
        reference_price = max(candle.high for candle in ordered[-stop_config.lookback_period :])
        buffered_reference = reference_price * (Decimal("1") + stop_config.stop_buffer)
        raw_distance = (buffered_reference - entry_price) / entry_price
        bounded_distance = _clamp(raw_distance, stop_config.min_stop_distance, stop_config.max_stop_distance)
        stop_price = entry_price * (Decimal("1") + bounded_distance)
        take_profit_price = entry_price * (Decimal("1") - bounded_distance * stop_config.take_profit_multiple)

    trailing_distance = (
        entry_price * stop_config.trailing_distance if stop_config.trailing_distance is not None else None
    )
    return StopMetrics(
        entry_price=entry_price,
        reference_price=reference_price,
        raw_stop_distance=raw_distance,
        bounded_stop_distance=bounded_distance,
        stop_price=stop_price,
        take_profit_price=take_profit_price,
        trailing_distance=trailing_distance,
    )


def plan_range_stop(
    series: MarketSeries,
    entry: EntrySignal,
    context: StrategyContext,
    config: Optional[StopPlanConfig] = None,
) -> Optional[StopPlan]:
    return RangeStopPlanner(config).plan_stop(series, entry, context)


def _entry_price(entry: EntrySignal, latest: Candle) -> Decimal:
    value = entry.metadata.get("latest_close") or entry.metadata.get("entry_price")
    if value is None:
        return latest.close
    try:
        price = Decimal(value)
    except Exception as exc:
        raise ValueError("entry metadata price must be Decimal-compatible") from exc
    if price <= Decimal("0"):
        raise ValueError("entry metadata price must be positive")
    return price


def _validate_candles(candles: tuple[Candle, ...], config: StopPlanConfig) -> None:
    if len(candles) < config.lookback_period:
        raise ValueError(
            "not enough candles for stop planning: "
            f"need {config.lookback_period}, got {len(candles)}"
        )
    previous_timestamp = candles[0].timestamp_ms
    for candle in candles[1:]:
        if candle.timestamp_ms <= previous_timestamp:
            raise ValueError("candles must be strictly ordered by timestamp")
        previous_timestamp = candle.timestamp_ms


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    if value < lower:
        return lower
    if value > upper:
        return upper
    return value


def _price(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _price_text(value: Decimal) -> str:
    return str(_price(value))


def _decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _require_positive_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value <= Decimal("0"):
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


__all__ = [
    "RangeStopPlanner",
    "StopMetrics",
    "StopPlanConfig",
    "calculate_stop_metrics",
    "plan_range_stop",
]
