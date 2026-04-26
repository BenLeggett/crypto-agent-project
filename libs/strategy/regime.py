"""Pure deterministic daily regime classification."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

from libs.strategy.interfaces import (
    Candle,
    MarketSeries,
    RegimeAssessment,
    RegimeLabel,
    StrategyContext,
)


@dataclass(frozen=True)
class RegimeFilterConfig:
    """Configuration for moving-average and slope based regime gating."""

    fast_ma_period: int = 5
    slow_ma_period: int = 20
    slope_period: int = 5
    trend_threshold: Decimal = Decimal("0.02")
    range_threshold: Decimal = Decimal("0.005")

    def __post_init__(self) -> None:
        for field_name in ("fast_ma_period", "slow_ma_period", "slope_period"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name} must be a positive integer")
        if self.fast_ma_period > self.slow_ma_period:
            raise ValueError("fast_ma_period must be less than or equal to slow_ma_period")
        _require_positive_decimal(self.trend_threshold, "trend_threshold")
        _require_positive_decimal(self.range_threshold, "range_threshold")
        if self.range_threshold >= self.trend_threshold:
            raise ValueError("range_threshold must be less than trend_threshold")

    @property
    def minimum_candles(self) -> int:
        return max(self.slow_ma_period, self.slope_period + 1)


@dataclass(frozen=True)
class RegimeMetrics:
    """Intermediate deterministic regime metrics for tests and reporting."""

    fast_ma: Decimal
    slow_ma: Decimal
    ma_spread: Decimal
    slope: Decimal
    latest_close: Decimal


class DailyRegimeClassifier:
    """Classify daily market regime from an ordered candle series."""

    def __init__(self, config: Optional[RegimeFilterConfig] = None) -> None:
        self.config = config or RegimeFilterConfig()

    def classify(self, series: MarketSeries, context: StrategyContext) -> RegimeAssessment:
        metrics = calculate_regime_metrics(series.candles, self.config)
        label = classify_regime(metrics, self.config)
        confidence = _confidence(label, metrics, self.config)
        return RegimeAssessment(
            label=label,
            confidence=confidence,
            as_of_ms=context.as_of_ms,
            reason=_reason(label, metrics),
            metadata={
                "symbol": series.symbol,
                "timeframe": series.timeframe,
                "fast_ma": _format_decimal(metrics.fast_ma),
                "slow_ma": _format_decimal(metrics.slow_ma),
                "ma_spread": _format_decimal(metrics.ma_spread),
                "slope": _format_decimal(metrics.slope),
                "latest_close": _format_decimal(metrics.latest_close),
                "fast_ma_period": str(self.config.fast_ma_period),
                "slow_ma_period": str(self.config.slow_ma_period),
                "slope_period": str(self.config.slope_period),
            },
        )


def calculate_regime_metrics(
    candles: Sequence[Candle],
    config: RegimeFilterConfig,
) -> RegimeMetrics:
    """Compute deterministic moving-average spread and price slope."""
    ordered = tuple(candles)
    _validate_candles(ordered, config)

    fast_ma = _average_close(ordered[-config.fast_ma_period :])
    slow_ma = _average_close(ordered[-config.slow_ma_period :])
    latest_close = ordered[-1].close
    prior_close = ordered[-(config.slope_period + 1)].close
    ma_spread = (fast_ma - slow_ma) / slow_ma
    slope = (latest_close - prior_close) / prior_close

    return RegimeMetrics(
        fast_ma=fast_ma,
        slow_ma=slow_ma,
        ma_spread=ma_spread,
        slope=slope,
        latest_close=latest_close,
    )


def classify_regime(metrics: RegimeMetrics, config: RegimeFilterConfig) -> RegimeLabel:
    """Classify metrics into a stable regime label."""
    if metrics.ma_spread >= config.trend_threshold and metrics.slope >= config.trend_threshold:
        return RegimeLabel.BULL
    if metrics.ma_spread <= -config.trend_threshold and metrics.slope <= -config.trend_threshold:
        return RegimeLabel.BEAR
    if abs(metrics.ma_spread) <= config.range_threshold and abs(metrics.slope) <= config.range_threshold:
        return RegimeLabel.RANGE
    return RegimeLabel.UNKNOWN


def classify_daily_regime(
    series: MarketSeries,
    context: StrategyContext,
    config: Optional[RegimeFilterConfig] = None,
) -> RegimeAssessment:
    """Convenience wrapper for callers that do not need a classifier instance."""
    return DailyRegimeClassifier(config).classify(series, context)


def _validate_candles(candles: tuple[Candle, ...], config: RegimeFilterConfig) -> None:
    if len(candles) < config.minimum_candles:
        raise ValueError(
            "not enough candles for regime classification: "
            f"need {config.minimum_candles}, got {len(candles)}"
        )
    previous_timestamp = candles[0].timestamp_ms
    for candle in candles[1:]:
        if candle.timestamp_ms <= previous_timestamp:
            raise ValueError("candles must be strictly ordered by timestamp")
        previous_timestamp = candle.timestamp_ms


def _average_close(candles: Sequence[Candle]) -> Decimal:
    total = sum((candle.close for candle in candles), Decimal("0"))
    return total / Decimal(len(candles))


def _confidence(
    label: RegimeLabel,
    metrics: RegimeMetrics,
    config: RegimeFilterConfig,
) -> Decimal:
    if label in {RegimeLabel.BULL, RegimeLabel.BEAR}:
        strength = (abs(metrics.ma_spread) + abs(metrics.slope)) / (config.trend_threshold * Decimal("2"))
        return _bounded_ratio(strength)
    if label is RegimeLabel.RANGE:
        movement = max(abs(metrics.ma_spread), abs(metrics.slope))
        strength = Decimal("1") - (movement / config.range_threshold)
        return _bounded_ratio(strength)
    return Decimal("0")


def _bounded_ratio(value: Decimal) -> Decimal:
    if value < Decimal("0"):
        return Decimal("0")
    if value > Decimal("1"):
        return Decimal("1")
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _reason(label: RegimeLabel, metrics: RegimeMetrics) -> str:
    return (
        f"{label.value} regime from ma_spread={_format_decimal(metrics.ma_spread)} "
        f"and slope={_format_decimal(metrics.slope)}"
    )


def _format_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _require_positive_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value <= Decimal("0"):
        raise ValueError(f"{field_name} must be positive")


__all__ = [
    "DailyRegimeClassifier",
    "RegimeFilterConfig",
    "RegimeMetrics",
    "calculate_regime_metrics",
    "classify_daily_regime",
    "classify_regime",
]
