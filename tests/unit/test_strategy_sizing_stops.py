from __future__ import annotations

from decimal import Decimal

import pytest

from libs.strategy.interfaces import (
    Candle,
    EntryDecision,
    EntrySignal,
    MarketSeries,
    SizingInput,
    StrategyContext,
    TradeSide,
)
from libs.strategy.sizing import (
    DeterministicPositionSizer,
    PositionSizingConfig,
    calculate_position_size,
    floor_to_step,
    size_position,
)
from libs.strategy.stops import (
    RangeStopPlanner,
    StopPlanConfig,
    calculate_stop_metrics,
    plan_range_stop,
)


SIZING_CONFIG = PositionSizingConfig(
    min_quantity=Decimal("0.001"),
    quantity_step=Decimal("0.001"),
    min_notional=Decimal("10"),
)

STOP_CONFIG = StopPlanConfig(
    lookback_period=3,
    stop_buffer=Decimal("0.001"),
    min_stop_distance=Decimal("0.01"),
    max_stop_distance=Decimal("0.05"),
    take_profit_multiple=Decimal("2"),
    trailing_distance=Decimal("0.02"),
)


def test_position_sizing_uses_risk_budget_and_quantity_step() -> None:
    result = size_position(
        SizingInput(
            symbol="BTC/USDT",
            side=TradeSide.LONG,
            equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
            entry_price=Decimal("100"),
            stop_price=Decimal("90"),
            max_position_value=Decimal("5000"),
        ),
        context(),
        SIZING_CONFIG,
    )

    assert result.quantity == Decimal("10.000")
    assert result.notional == Decimal("1000.0000")
    assert result.risk_amount == Decimal("100.0000")
    assert result.metadata["risk_budget"] == "100.0000"
    assert result.metadata["quantity_step"] == "0.001"


def test_position_sizing_caps_by_max_notional() -> None:
    result = DeterministicPositionSizer(SIZING_CONFIG).size(
        SizingInput(
            symbol="BTC/USDT",
            side=TradeSide.LONG,
            equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
            entry_price=Decimal("100"),
            stop_price=Decimal("90"),
            max_position_value=Decimal("250"),
        ),
        context(),
    )

    assert result.quantity == Decimal("2.500")
    assert result.notional == Decimal("250.0000")
    assert result.risk_amount == Decimal("25.0000")


def test_position_sizing_returns_zero_when_below_minimums() -> None:
    result = size_position(
        SizingInput(
            symbol="BTC/USDT",
            side=TradeSide.LONG,
            equity=Decimal("100"),
            risk_fraction=Decimal("0.001"),
            entry_price=Decimal("100"),
            stop_price=Decimal("90"),
            max_position_value=Decimal("5"),
        ),
        context(),
        SIZING_CONFIG,
    )

    assert result.quantity == Decimal("0")
    assert result.notional == Decimal("0.0000")
    assert result.risk_amount == Decimal("0.0000")
    assert "below configured minimums" in result.reason


def test_sizing_intermediates_and_config_validate_bounds() -> None:
    sizing_input = SizingInput(
        symbol="BTC/USDT",
        side=TradeSide.SHORT,
        equity=Decimal("10000"),
        risk_fraction=Decimal("0.01"),
        entry_price=Decimal("100"),
        stop_price=Decimal("110"),
        max_position_value=Decimal("5000"),
    )

    first = calculate_position_size(sizing_input, SIZING_CONFIG)
    second = calculate_position_size(sizing_input, SIZING_CONFIG)

    assert first == second
    assert first.per_unit_risk == Decimal("10")
    assert first.raw_quantity == Decimal("10")
    assert floor_to_step(Decimal("1.2349"), Decimal("0.01")) == Decimal("1.23")

    with pytest.raises(ValueError, match="quantity_step"):
        PositionSizingConfig(quantity_step=Decimal("0"))
    with pytest.raises(TypeError, match="Decimal"):
        PositionSizingConfig(min_notional="10")  # type: ignore[arg-type]


def test_plans_long_range_stop_with_bounded_distance_and_target() -> None:
    plan = plan_range_stop(
        series_from_closes("100", "101", "102"),
        entry_signal(TradeSide.LONG, "102"),
        context(),
        STOP_CONFIG,
    )

    assert plan is not None
    assert plan.side is TradeSide.LONG
    assert plan.stop_price == Decimal("99.9000")
    assert plan.take_profit_price == Decimal("106.2000")
    assert plan.trailing_distance == Decimal("2.0400")
    assert plan.metadata["bounded_stop_distance"] == "0.0206"


def test_plans_short_range_stop_with_bounded_distance_and_target() -> None:
    plan = RangeStopPlanner(STOP_CONFIG).plan_stop(
        series_from_closes("102", "101", "100"),
        entry_signal(TradeSide.SHORT, "100"),
        context(),
    )

    assert plan is not None
    assert plan.side is TradeSide.SHORT
    assert plan.stop_price == Decimal("102.1020")
    assert plan.take_profit_price == Decimal("95.7960")
    assert plan.metadata["reference_price"] == "102.0000"


def test_stop_planner_returns_none_for_hold_signal() -> None:
    plan = plan_range_stop(
        series_from_closes("100", "101", "102"),
        EntrySignal(
            symbol="BTC/USDT",
            timeframe="4h",
            action=EntryDecision.HOLD,
            side=None,
            strength=Decimal("0"),
            timestamp_ms=1_700_028_800_000,
            reason="no entry",
        ),
        context(),
        STOP_CONFIG,
    )

    assert plan is None


def test_stop_metrics_and_config_validate_bounds() -> None:
    signal = entry_signal(TradeSide.LONG, "102")
    first = calculate_stop_metrics(series_from_closes("100", "101", "102").candles, signal, STOP_CONFIG)
    second = calculate_stop_metrics(series_from_closes("100", "101", "102").candles, signal, STOP_CONFIG)

    assert first == second
    assert first.entry_price == Decimal("102")
    assert first.reference_price == Decimal("100")

    with pytest.raises(ValueError, match="not enough candles"):
        calculate_stop_metrics(series_from_closes("100", "101").candles, signal, STOP_CONFIG)
    with pytest.raises(ValueError, match="lookback_period"):
        StopPlanConfig(lookback_period=0)
    with pytest.raises(ValueError, match="min_stop_distance"):
        StopPlanConfig(min_stop_distance=Decimal("0.10"), max_stop_distance=Decimal("0.05"))
    with pytest.raises(TypeError, match="Decimal"):
        StopPlanConfig(stop_buffer="0.01")  # type: ignore[arg-type]


def context() -> StrategyContext:
    return StrategyContext(
        run_id="run-001",
        config_hash="config-sha256",
        as_of_ms=1_700_043_200_000,
    )


def entry_signal(side: TradeSide, latest_close: str) -> EntrySignal:
    return EntrySignal(
        symbol="BTC/USDT",
        timeframe="4h",
        action=EntryDecision.ENTER,
        side=side,
        strength=Decimal("0.80"),
        timestamp_ms=1_700_043_200_000,
        reason="entry fixture",
        metadata={"latest_close": latest_close},
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
