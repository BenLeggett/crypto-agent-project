from __future__ import annotations

from decimal import Decimal

import pytest

from libs.strategy.breakout import BreakoutSignalConfig, BreakoutSignalGenerator
from libs.strategy.interfaces import (
    Candle,
    EntryDecision,
    MarketSeries,
    RegimeAssessment,
    RegimeLabel,
    StrategyContext,
)
from libs.strategy.signal_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    DeterministicSignalSnapshotBuilder,
    SignalSnapshotSizingConfig,
    build_signal_snapshot,
    serialize_strategy_snapshot,
)
from libs.strategy.sizing import DeterministicPositionSizer, PositionSizingConfig
from libs.strategy.stops import RangeStopPlanner, StopPlanConfig


BREAKOUT_CONFIG = BreakoutSignalConfig(
    lookback_period=3,
    momentum_period=2,
    breakout_buffer=Decimal("0.01"),
    breakdown_buffer=Decimal("0.01"),
    minimum_momentum=Decimal("0.01"),
)

STOP_CONFIG = StopPlanConfig(
    lookback_period=3,
    stop_buffer=Decimal("0.001"),
    min_stop_distance=Decimal("0.01"),
    max_stop_distance=Decimal("0.05"),
    take_profit_multiple=Decimal("2"),
)

SIZING_CONFIG = SignalSnapshotSizingConfig(
    equity=Decimal("10000"),
    risk_fraction=Decimal("0.01"),
    max_position_value=Decimal("5000"),
)


def test_builds_entry_snapshot_with_stop_and_position_size() -> None:
    builder = DeterministicSignalSnapshotBuilder(
        regime_classifier=FixedRegimeClassifier(RegimeLabel.BULL),
        entry_generator=BreakoutSignalGenerator(BREAKOUT_CONFIG),
        exit_generator=BreakoutSignalGenerator(BREAKOUT_CONFIG),
        stop_planner=RangeStopPlanner(STOP_CONFIG),
        position_sizer=DeterministicPositionSizer(PositionSizingConfig(quantity_step=Decimal("0.001"))),
        sizing_config=SIZING_CONFIG,
    )

    snapshot = builder.build_snapshot(series_from_closes("100", "101", "102", "105"), context())

    assert snapshot.symbol == "BTC/USDT"
    assert snapshot.timeframe == "4h"
    assert snapshot.config_hash == "config-sha256"
    assert snapshot.regime.label is RegimeLabel.BULL
    assert snapshot.entry.action is EntryDecision.ENTER
    assert snapshot.stop_plan is not None
    assert snapshot.sizing_input is not None
    assert snapshot.position_size is not None
    assert snapshot.metadata["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert snapshot.position_size.quantity > Decimal("0")


def test_builds_hold_snapshot_without_sizing_or_stop() -> None:
    snapshot = build_signal_snapshot(
        series_from_closes("100", "101", "102", "105"),
        context(),
        regime_classifier=FixedRegimeClassifier(RegimeLabel.RANGE),
        entry_generator=BreakoutSignalGenerator(BREAKOUT_CONFIG),
        exit_generator=BreakoutSignalGenerator(BREAKOUT_CONFIG),
        stop_planner=RangeStopPlanner(STOP_CONFIG),
        position_sizer=DeterministicPositionSizer(),
    )

    assert snapshot.entry.action is EntryDecision.HOLD
    assert snapshot.stop_plan is None
    assert snapshot.sizing_input is None
    assert snapshot.position_size is None


def test_serialized_snapshot_is_stable_and_machine_readable() -> None:
    builder = DeterministicSignalSnapshotBuilder(
        regime_classifier=FixedRegimeClassifier(RegimeLabel.BULL),
        entry_generator=BreakoutSignalGenerator(BREAKOUT_CONFIG),
        exit_generator=BreakoutSignalGenerator(BREAKOUT_CONFIG),
        stop_planner=RangeStopPlanner(STOP_CONFIG),
        position_sizer=DeterministicPositionSizer(PositionSizingConfig(quantity_step=Decimal("0.001"))),
        sizing_config=SIZING_CONFIG,
    )
    snapshot = builder.build_snapshot(series_from_closes("100", "101", "102", "105"), context())

    first = serialize_strategy_snapshot(snapshot)
    second = serialize_strategy_snapshot(snapshot)

    assert first == second
    assert first["schema_version"] == SNAPSHOT_SCHEMA_VERSION
    assert first["regime"]["label"] == "bull"
    assert first["entry"]["action"] == "enter"
    assert first["entry"]["side"] == "long"
    assert first["stop_plan"]["stop_price"] == "100.899"
    assert first["sizing_input"]["entry_price"] == "105"
    assert first["config_hash"] == "config-sha256"
    assert first["metadata"]["latest_close"] == "105"


def test_entry_snapshot_requires_sizing_config() -> None:
    builder = DeterministicSignalSnapshotBuilder(
        regime_classifier=FixedRegimeClassifier(RegimeLabel.BULL),
        entry_generator=BreakoutSignalGenerator(BREAKOUT_CONFIG),
        exit_generator=BreakoutSignalGenerator(BREAKOUT_CONFIG),
        stop_planner=RangeStopPlanner(STOP_CONFIG),
        position_sizer=DeterministicPositionSizer(),
    )

    with pytest.raises(ValueError, match="sizing_config"):
        builder.build_snapshot(series_from_closes("100", "101", "102", "105"), context())


def test_signal_snapshot_sizing_config_validates_bounds() -> None:
    with pytest.raises(ValueError, match="equity"):
        SignalSnapshotSizingConfig(
            equity=Decimal("0"),
            risk_fraction=Decimal("0.01"),
            max_position_value=Decimal("1000"),
        )

    with pytest.raises(ValueError, match="between 0 and 1"):
        SignalSnapshotSizingConfig(
            equity=Decimal("1000"),
            risk_fraction=Decimal("2"),
            max_position_value=Decimal("1000"),
        )

    with pytest.raises(TypeError, match="Decimal"):
        SignalSnapshotSizingConfig(
            equity="1000",  # type: ignore[arg-type]
            risk_fraction=Decimal("0.01"),
            max_position_value=Decimal("1000"),
        )


class FixedRegimeClassifier:
    def __init__(self, label: RegimeLabel) -> None:
        self.label = label

    def classify(self, series: MarketSeries, context: StrategyContext) -> RegimeAssessment:
        return RegimeAssessment(
            label=self.label,
            confidence=Decimal("0.80"),
            as_of_ms=context.as_of_ms,
            reason=f"{self.label.value} fixture",
            metadata={"symbol": series.symbol, "timeframe": series.timeframe},
        )


def context() -> StrategyContext:
    return StrategyContext(
        run_id="run-001",
        config_hash="config-sha256",
        as_of_ms=1_700_043_200_000,
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
