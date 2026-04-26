"""Pure deterministic breakout entry and exit signals."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional, Sequence

from libs.strategy.interfaces import (
    Candle,
    EntryDecision,
    EntrySignal,
    ExitDecision,
    ExitSignal,
    MarketSeries,
    RegimeAssessment,
    RegimeLabel,
    StrategyContext,
    TradeSide,
)


@dataclass(frozen=True)
class BreakoutSignalConfig:
    """Configuration for deterministic breakout/trend signals."""

    lookback_period: int = 20
    momentum_period: int = 3
    breakout_buffer: Decimal = Decimal("0.001")
    breakdown_buffer: Decimal = Decimal("0.001")
    minimum_momentum: Decimal = Decimal("0.005")
    allow_short: bool = False
    allowed_entry_regimes: tuple[RegimeLabel, ...] = (RegimeLabel.BULL,)
    exit_on_regimes: tuple[RegimeLabel, ...] = (RegimeLabel.BEAR, RegimeLabel.UNKNOWN)

    def __post_init__(self) -> None:
        for field_name in ("lookback_period", "momentum_period"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or value < 1:
                raise ValueError(f"{field_name} must be a positive integer")
        _require_non_negative_decimal(self.breakout_buffer, "breakout_buffer")
        _require_non_negative_decimal(self.breakdown_buffer, "breakdown_buffer")
        _require_non_negative_decimal(self.minimum_momentum, "minimum_momentum")
        object.__setattr__(self, "allowed_entry_regimes", tuple(self.allowed_entry_regimes))
        object.__setattr__(self, "exit_on_regimes", tuple(self.exit_on_regimes))

    @property
    def minimum_candles(self) -> int:
        return max(self.lookback_period + 1, self.momentum_period + 1)


@dataclass(frozen=True)
class BreakoutMetrics:
    """Intermediate deterministic breakout metrics for tests and snapshots."""

    prior_high: Decimal
    prior_low: Decimal
    latest_close: Decimal
    close_vs_prior_high: Decimal
    close_vs_prior_low: Decimal
    momentum: Decimal


class BreakoutSignalGenerator:
    """Generate deterministic entry and exit signals from market series."""

    def __init__(self, config: Optional[BreakoutSignalConfig] = None) -> None:
        self.config = config or BreakoutSignalConfig()

    def generate_entry(
        self,
        series: MarketSeries,
        regime: RegimeAssessment,
        context: StrategyContext,
    ) -> EntrySignal:
        metrics = calculate_breakout_metrics(series.candles, self.config)
        if regime.label not in self.config.allowed_entry_regimes:
            return _entry_hold(series, context, metrics, self.config, "regime does not allow new breakout entries")

        long_breakout = (
            metrics.close_vs_prior_high >= self.config.breakout_buffer
            and metrics.momentum >= self.config.minimum_momentum
        )
        if long_breakout:
            return EntrySignal(
                symbol=series.symbol,
                timeframe=series.timeframe,
                action=EntryDecision.ENTER,
                side=TradeSide.LONG,
                strength=_strength(metrics.close_vs_prior_high, metrics.momentum),
                timestamp_ms=context.as_of_ms,
                reason=_reason("long breakout confirmed", metrics),
                metadata=_metadata(metrics, self.config),
            )

        if self.config.allow_short and regime.label is RegimeLabel.BEAR:
            short_breakout = (
                metrics.close_vs_prior_low <= -self.config.breakout_buffer
                and metrics.momentum <= -self.config.minimum_momentum
            )
            if short_breakout:
                return EntrySignal(
                    symbol=series.symbol,
                    timeframe=series.timeframe,
                    action=EntryDecision.ENTER,
                    side=TradeSide.SHORT,
                    strength=_strength(abs(metrics.close_vs_prior_low), abs(metrics.momentum)),
                    timestamp_ms=context.as_of_ms,
                    reason=_reason("short breakdown confirmed", metrics),
                    metadata=_metadata(metrics, self.config),
                )

        return _entry_hold(series, context, metrics, self.config, "no breakout entry condition")

    def generate_exit(
        self,
        series: MarketSeries,
        regime: RegimeAssessment,
        context: StrategyContext,
        side: TradeSide = TradeSide.LONG,
    ) -> ExitSignal:
        metrics = calculate_breakout_metrics(series.candles, self.config)
        if regime.label in self.config.exit_on_regimes:
            return _exit_signal(series, context, side, metrics, self.config, "regime requires exit")

        if side is TradeSide.LONG:
            breakdown = metrics.close_vs_prior_low <= -self.config.breakdown_buffer
            momentum_reversal = metrics.momentum <= -self.config.minimum_momentum
        else:
            breakdown = metrics.close_vs_prior_high >= self.config.breakdown_buffer
            momentum_reversal = metrics.momentum >= self.config.minimum_momentum

        if breakdown:
            return _exit_signal(series, context, side, metrics, self.config, "breakout structure failed")
        if momentum_reversal:
            return _exit_signal(series, context, side, metrics, self.config, "momentum reversed")

        return ExitSignal(
            symbol=series.symbol,
            timeframe=series.timeframe,
            action=ExitDecision.HOLD,
            side=None,
            strength=Decimal("0"),
            timestamp_ms=context.as_of_ms,
            reason=_reason("no exit condition", metrics),
            metadata=_metadata(metrics, self.config),
        )


def calculate_breakout_metrics(
    candles: Sequence[Candle],
    config: BreakoutSignalConfig,
) -> BreakoutMetrics:
    """Compute prior-range breakout metrics from ordered candles."""
    ordered = tuple(candles)
    _validate_candles(ordered, config)

    latest = ordered[-1]
    lookback = ordered[-(config.lookback_period + 1) : -1]
    prior_high = max(candle.high for candle in lookback)
    prior_low = min(candle.low for candle in lookback)
    momentum_base = ordered[-(config.momentum_period + 1)].close

    return BreakoutMetrics(
        prior_high=prior_high,
        prior_low=prior_low,
        latest_close=latest.close,
        close_vs_prior_high=(latest.close - prior_high) / prior_high,
        close_vs_prior_low=(latest.close - prior_low) / prior_low,
        momentum=(latest.close - momentum_base) / momentum_base,
    )


def generate_breakout_entry(
    series: MarketSeries,
    regime: RegimeAssessment,
    context: StrategyContext,
    config: Optional[BreakoutSignalConfig] = None,
) -> EntrySignal:
    return BreakoutSignalGenerator(config).generate_entry(series, regime, context)


def generate_breakout_exit(
    series: MarketSeries,
    regime: RegimeAssessment,
    context: StrategyContext,
    side: TradeSide = TradeSide.LONG,
    config: Optional[BreakoutSignalConfig] = None,
) -> ExitSignal:
    return BreakoutSignalGenerator(config).generate_exit(series, regime, context, side)


def _validate_candles(candles: tuple[Candle, ...], config: BreakoutSignalConfig) -> None:
    if len(candles) < config.minimum_candles:
        raise ValueError(
            "not enough candles for breakout signals: "
            f"need {config.minimum_candles}, got {len(candles)}"
        )
    previous_timestamp = candles[0].timestamp_ms
    for candle in candles[1:]:
        if candle.timestamp_ms <= previous_timestamp:
            raise ValueError("candles must be strictly ordered by timestamp")
        previous_timestamp = candle.timestamp_ms


def _entry_hold(
    series: MarketSeries,
    context: StrategyContext,
    metrics: BreakoutMetrics,
    config: BreakoutSignalConfig,
    reason: str,
) -> EntrySignal:
    return EntrySignal(
        symbol=series.symbol,
        timeframe=series.timeframe,
        action=EntryDecision.HOLD,
        side=None,
        strength=Decimal("0"),
        timestamp_ms=context.as_of_ms,
        reason=_reason(reason, metrics),
        metadata=_metadata(metrics, config),
    )


def _exit_signal(
    series: MarketSeries,
    context: StrategyContext,
    side: TradeSide,
    metrics: BreakoutMetrics,
    config: BreakoutSignalConfig,
    reason: str,
) -> ExitSignal:
    return ExitSignal(
        symbol=series.symbol,
        timeframe=series.timeframe,
        action=ExitDecision.EXIT,
        side=side,
        strength=_strength(max(abs(metrics.close_vs_prior_low), abs(metrics.close_vs_prior_high)), abs(metrics.momentum)),
        timestamp_ms=context.as_of_ms,
        reason=_reason(reason, metrics),
        metadata=_metadata(metrics, config),
    )


def _strength(first: Decimal, second: Decimal) -> Decimal:
    combined = (first + second) / Decimal("2")
    if combined < Decimal("0"):
        return Decimal("0")
    if combined > Decimal("1"):
        return Decimal("1")
    return combined.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _reason(prefix: str, metrics: BreakoutMetrics) -> str:
    return (
        f"{prefix}: close_vs_prior_high={_format_decimal(metrics.close_vs_prior_high)}, "
        f"close_vs_prior_low={_format_decimal(metrics.close_vs_prior_low)}, "
        f"momentum={_format_decimal(metrics.momentum)}"
    )


def _metadata(metrics: BreakoutMetrics, config: BreakoutSignalConfig) -> dict[str, str]:
    return {
        "prior_high": _format_decimal(metrics.prior_high),
        "prior_low": _format_decimal(metrics.prior_low),
        "latest_close": _format_decimal(metrics.latest_close),
        "close_vs_prior_high": _format_decimal(metrics.close_vs_prior_high),
        "close_vs_prior_low": _format_decimal(metrics.close_vs_prior_low),
        "momentum": _format_decimal(metrics.momentum),
        "lookback_period": str(config.lookback_period),
        "momentum_period": str(config.momentum_period),
    }


def _format_decimal(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def _require_non_negative_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


__all__ = [
    "BreakoutMetrics",
    "BreakoutSignalConfig",
    "BreakoutSignalGenerator",
    "calculate_breakout_metrics",
    "generate_breakout_entry",
    "generate_breakout_exit",
]
