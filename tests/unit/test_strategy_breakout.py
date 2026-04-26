from __future__ import annotations

from decimal import Decimal

import pytest

from libs.strategy.breakout import (
    BreakoutSignalConfig,
    BreakoutSignalGenerator,
    calculate_breakout_metrics,
    generate_breakout_entry,
    generate_breakout_exit,
)
from libs.strategy.interfaces import (
    Candle,
    EntryDecision,
    ExitDecision,
    MarketSeries,
    RegimeAssessment,
    RegimeLabel,
    StrategyContext,
    TradeSide,
)


CONFIG = BreakoutSignalConfig(
    lookback_period=3,
    momentum_period=2,
    breakout_buffer=Decimal("0.01"),
    breakdown_buffer=Decimal("0.01"),
    minimum_momentum=Decimal("0.01"),
)


def test_generates_long_entry_when_bull_regime_breaks_prior_high() -> None:
    signal = generate_breakout_entry(
        series_from_closes("100", "101", "102", "105"),
        regime(RegimeLabel.BULL),
        context(),
        CONFIG,
    )

    assert signal.action is EntryDecision.ENTER
    assert signal.side is TradeSide.LONG
    assert signal.strength > Decimal("0")
    assert signal.metadata["prior_high"] == "102.0000"
    assert Decimal(signal.metadata["close_vs_prior_high"]) >= CONFIG.breakout_buffer


def test_holds_entry_when_regime_does_not_allow_entries() -> None:
    signal = generate_breakout_entry(
        series_from_closes("100", "101", "102", "105"),
        regime(RegimeLabel.RANGE),
        context(),
        CONFIG,
    )

    assert signal.action is EntryDecision.HOLD
    assert signal.side is None
    assert signal.strength == Decimal("0")
    assert "regime does not allow" in signal.reason


def test_holds_entry_when_breakout_or_momentum_is_missing() -> None:
    signal = BreakoutSignalGenerator(CONFIG).generate_entry(
        series_from_closes("100", "101", "102", "102.5"),
        regime(RegimeLabel.BULL),
        context(),
    )

    assert signal.action is EntryDecision.HOLD
    assert signal.side is None
    assert "no breakout" in signal.reason


def test_generates_long_exit_on_breakdown() -> None:
    signal = generate_breakout_exit(
        series_from_closes("100", "99", "98", "95"),
        regime(RegimeLabel.BULL),
        context(),
        TradeSide.LONG,
        CONFIG,
    )

    assert signal.action is ExitDecision.EXIT
    assert signal.side is TradeSide.LONG
    assert "breakout structure failed" in signal.reason
    assert Decimal(signal.metadata["close_vs_prior_low"]) <= -CONFIG.breakdown_buffer


def test_generates_exit_when_regime_requires_it() -> None:
    signal = generate_breakout_exit(
        series_from_closes("100", "101", "102", "103"),
        regime(RegimeLabel.BEAR),
        context(),
        TradeSide.LONG,
        CONFIG,
    )

    assert signal.action is ExitDecision.EXIT
    assert signal.side is TradeSide.LONG
    assert "regime requires exit" in signal.reason


def test_can_generate_short_entry_when_explicitly_configured() -> None:
    short_config = BreakoutSignalConfig(
        lookback_period=3,
        momentum_period=2,
        breakout_buffer=Decimal("0.01"),
        breakdown_buffer=Decimal("0.01"),
        minimum_momentum=Decimal("0.01"),
        allow_short=True,
        allowed_entry_regimes=(RegimeLabel.BEAR,),
    )

    signal = generate_breakout_entry(
        series_from_closes("105", "103", "101", "98"),
        regime(RegimeLabel.BEAR),
        context(),
        short_config,
    )

    assert signal.action is EntryDecision.ENTER
    assert signal.side is TradeSide.SHORT
    assert Decimal(signal.metadata["close_vs_prior_low"]) <= -short_config.breakout_buffer


def test_breakout_metrics_are_deterministic() -> None:
    series = series_from_closes("100", "101", "102", "105")

    first = calculate_breakout_metrics(series.candles, CONFIG)
    second = calculate_breakout_metrics(series.candles, CONFIG)

    assert first == second
    assert first.prior_high == Decimal("102")
    assert first.prior_low == Decimal("100")
    assert first.latest_close == Decimal("105")


def test_breakout_validation_fails_fast() -> None:
    with pytest.raises(ValueError, match="not enough candles"):
        calculate_breakout_metrics(series_from_closes("100", "101").candles, CONFIG)

    unordered = MarketSeries(
        symbol="BTC/USDT",
        timeframe="4h",
        candles=(
            candle(1_700_000_000_000, "100"),
            candle(1_700_014_400_000, "101"),
            candle(1_700_028_800_000, "102"),
            candle(1_700_014_400_000, "105"),
        ),
    )
    with pytest.raises(ValueError, match="strictly ordered"):
        calculate_breakout_metrics(unordered.candles, CONFIG)

    with pytest.raises(ValueError, match="lookback_period"):
        BreakoutSignalConfig(lookback_period=0)

    with pytest.raises(TypeError, match="Decimal"):
        BreakoutSignalConfig(breakout_buffer="0.01")  # type: ignore[arg-type]


def context() -> StrategyContext:
    return StrategyContext(
        run_id="run-001",
        config_hash="config-sha256",
        as_of_ms=1_700_043_200_000,
    )


def regime(label: RegimeLabel) -> RegimeAssessment:
    return RegimeAssessment(
        label=label,
        confidence=Decimal("0.80"),
        as_of_ms=1_700_043_200_000,
        reason=f"{label.value} fixture",
    )


def series_from_closes(*closes: str) -> MarketSeries:
    return MarketSeries(
        symbol="BTC/USDT",
        timeframe="4h",
        candles=tuple(
            candle(1_700_000_000_000 + index * 14_400_000, close)
            for index, close in enumerate(closes)
        ),
    )


def candle(timestamp_ms: int, close: str) -> Candle:
    close_value = Decimal(close)
    return Candle(
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp_ms=timestamp_ms,
        open=close_value,
        high=close_value,
        low=close_value,
        close=close_value,
        volume=Decimal("100"),
    )
