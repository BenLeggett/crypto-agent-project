from __future__ import annotations

from decimal import Decimal

import pytest

from libs.strategy.interfaces import Candle, MarketSeries, RegimeLabel, StrategyContext
from libs.strategy.regime import (
    DailyRegimeClassifier,
    RegimeFilterConfig,
    calculate_regime_metrics,
    classify_daily_regime,
)


CONFIG = RegimeFilterConfig(
    fast_ma_period=3,
    slow_ma_period=5,
    slope_period=3,
    trend_threshold=Decimal("0.02"),
    range_threshold=Decimal("0.005"),
)


def test_classifies_bull_regime_from_rising_ma_and_slope() -> None:
    assessment = classify_daily_regime(series_from_closes("100", "101", "102", "110", "115"), context(), CONFIG)

    assert assessment.label is RegimeLabel.BULL
    assert assessment.confidence == Decimal("1")
    assert assessment.metadata["symbol"] == "BTC/USDT"
    assert assessment.metadata["timeframe"] == "1d"
    assert assessment.metadata["fast_ma_period"] == "3"
    assert "ma_spread" in assessment.reason


def test_classifies_bear_regime_from_falling_ma_and_slope() -> None:
    assessment = DailyRegimeClassifier(CONFIG).classify(
        series_from_closes("115", "110", "108", "101", "95"),
        context(),
    )

    assert assessment.label is RegimeLabel.BEAR
    assert assessment.confidence == Decimal("1")
    assert Decimal(assessment.metadata["ma_spread"]) < Decimal("0")
    assert Decimal(assessment.metadata["slope"]) < Decimal("0")


def test_classifies_range_regime_when_ma_and_slope_are_flat() -> None:
    assessment = classify_daily_regime(
        series_from_closes("100", "100.1", "99.9", "100", "100"),
        context(),
        CONFIG,
    )

    assert assessment.label is RegimeLabel.RANGE
    assert assessment.confidence > Decimal("0")
    assert abs(Decimal(assessment.metadata["ma_spread"])) <= CONFIG.range_threshold
    assert abs(Decimal(assessment.metadata["slope"])) <= CONFIG.range_threshold


def test_classifies_unknown_when_metrics_conflict() -> None:
    assessment = classify_daily_regime(
        series_from_closes("100", "130", "130", "130", "125"),
        context(),
        CONFIG,
    )

    assert assessment.label is RegimeLabel.UNKNOWN
    assert assessment.confidence == Decimal("0")
    assert Decimal(assessment.metadata["ma_spread"]) > Decimal("0")
    assert Decimal(assessment.metadata["slope"]) < Decimal("0")


def test_regime_metrics_are_deterministic() -> None:
    series = series_from_closes("100", "101", "102", "110", "115")

    first = calculate_regime_metrics(series.candles, CONFIG)
    second = calculate_regime_metrics(series.candles, CONFIG)

    assert first == second
    assert first.fast_ma == Decimal("109")
    assert first.slow_ma == Decimal("105.6")
    assert first.latest_close == Decimal("115")


def test_regime_classifier_fails_fast_on_insufficient_or_unordered_candles() -> None:
    with pytest.raises(ValueError, match="not enough candles"):
        calculate_regime_metrics(series_from_closes("100", "101").candles, CONFIG)

    unordered = MarketSeries(
        symbol="BTC/USDT",
        timeframe="1d",
        candles=(
            candle(1_700_000_000_000, "100"),
            candle(1_700_000_086_400, "101"),
            candle(1_700_000_172_800, "102"),
            candle(1_700_000_259_200, "103"),
            candle(1_700_000_172_800, "104"),
        ),
    )
    with pytest.raises(ValueError, match="strictly ordered"):
        calculate_regime_metrics(unordered.candles, CONFIG)


def test_regime_config_validates_bounds() -> None:
    with pytest.raises(ValueError, match="fast_ma_period"):
        RegimeFilterConfig(fast_ma_period=0)

    with pytest.raises(ValueError, match="fast_ma_period must be less"):
        RegimeFilterConfig(fast_ma_period=10, slow_ma_period=5)

    with pytest.raises(ValueError, match="range_threshold"):
        RegimeFilterConfig(
            trend_threshold=Decimal("0.01"),
            range_threshold=Decimal("0.01"),
        )

    with pytest.raises(TypeError, match="Decimal"):
        RegimeFilterConfig(trend_threshold="0.02")  # type: ignore[arg-type]


def context() -> StrategyContext:
    return StrategyContext(
        run_id="run-001",
        config_hash="config-sha256",
        as_of_ms=1_700_000_345_600,
    )


def series_from_closes(*closes: str) -> MarketSeries:
    return MarketSeries(
        symbol="BTC/USDT",
        timeframe="1d",
        candles=tuple(
            candle(1_700_000_000_000 + index * 86_400_000, close)
            for index, close in enumerate(closes)
        ),
    )


def candle(timestamp_ms: int, close: str) -> Candle:
    close_value = Decimal(close)
    return Candle(
        symbol="BTC/USDT",
        timeframe="1d",
        timestamp_ms=timestamp_ms,
        open=close_value,
        high=close_value,
        low=close_value,
        close=close_value,
        volume=Decimal("100"),
    )
