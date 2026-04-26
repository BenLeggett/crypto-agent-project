from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from libs.strategy.interfaces import (
    Candle,
    EntryDecision,
    EntrySignal,
    ExitDecision,
    ExitSignal,
    MarketSeries,
    PositionSize,
    RegimeAssessment,
    RegimeLabel,
    SizingInput,
    StopPlan,
    StrategyContext,
    StrategySnapshot,
    TradeSide,
)


def candle(timestamp_ms: int = 1_700_000_000_000) -> Candle:
    return Candle(
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp_ms=timestamp_ms,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("105"),
        volume=Decimal("42"),
    )


def strategy_context() -> StrategyContext:
    return StrategyContext(
        run_id="run-001",
        config_hash="config-sha256",
        as_of_ms=1_700_000_000_000,
        metadata={"mode": "paper"},
    )


def regime() -> RegimeAssessment:
    return RegimeAssessment(
        label=RegimeLabel.BULL,
        confidence=Decimal("0.80"),
        as_of_ms=1_700_000_000_000,
        reason="trend filter accepted",
    )


def entry_signal() -> EntrySignal:
    return EntrySignal(
        symbol="BTC/USDT",
        timeframe="4h",
        action=EntryDecision.ENTER,
        side=TradeSide.LONG,
        strength=Decimal("0.70"),
        timestamp_ms=1_700_000_000_000,
        reason="breakout confirmed",
    )


def exit_signal() -> ExitSignal:
    return ExitSignal(
        symbol="BTC/USDT",
        timeframe="4h",
        action=ExitDecision.HOLD,
        side=None,
        strength=Decimal("0.10"),
        timestamp_ms=1_700_000_000_000,
        reason="no exit condition",
    )


def stop_plan() -> StopPlan:
    return StopPlan(
        symbol="BTC/USDT",
        side=TradeSide.LONG,
        stop_price=Decimal("90"),
        take_profit_price=Decimal("130"),
        trailing_distance=None,
        reason="fixed risk multiple",
    )


def sizing_input() -> SizingInput:
    return SizingInput(
        symbol="BTC/USDT",
        side=TradeSide.LONG,
        equity=Decimal("10000"),
        risk_fraction=Decimal("0.01"),
        entry_price=Decimal("105"),
        stop_price=Decimal("90"),
        max_position_value=Decimal("1000"),
    )


def position_size() -> PositionSize:
    return PositionSize(
        symbol="BTC/USDT",
        side=TradeSide.LONG,
        quantity=Decimal("0.25"),
        notional=Decimal("26.25"),
        risk_amount=Decimal("3.75"),
        reason="risk capped",
    )


def strategy_snapshot() -> StrategySnapshot:
    return StrategySnapshot(
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp_ms=1_700_000_000_000,
        config_hash="config-sha256",
        regime=regime(),
        entry=entry_signal(),
        exit=exit_signal(),
        sizing_input=sizing_input(),
        position_size=position_size(),
        stop_plan=stop_plan(),
        metadata={"source": "unit-test"},
    )


def test_strategy_records_are_immutable_and_deterministic() -> None:
    first = strategy_snapshot()
    second = strategy_snapshot()

    assert first == second
    assert first.config_hash == "config-sha256"
    assert first.metadata["source"] == "unit-test"
    with pytest.raises(FrozenInstanceError):
        first.config_hash = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        first.metadata["source"] = "changed"  # type: ignore[index]


def test_market_series_requires_single_symbol_and_timeframe() -> None:
    series = MarketSeries(symbol="BTC/USDT", timeframe="4h", candles=[candle()])

    assert isinstance(series.candles, tuple)
    assert series.candles[0].close == Decimal("105")

    bad_candle = Candle(
        symbol="ETH/USDT",
        timeframe="4h",
        timestamp_ms=1_700_000_000_000,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("95"),
        close=Decimal("105"),
        volume=Decimal("42"),
    )
    with pytest.raises(ValueError, match="series symbol"):
        MarketSeries(symbol="BTC/USDT", timeframe="4h", candles=[bad_candle])


def test_interfaces_fail_fast_on_invalid_values() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        RegimeAssessment(
            label=RegimeLabel.BULL,
            confidence=Decimal("1.50"),
            as_of_ms=1,
            reason="invalid confidence",
        )

    with pytest.raises(ValueError, match="side is required"):
        EntrySignal(
            symbol="BTC/USDT",
            timeframe="4h",
            action=EntryDecision.ENTER,
            side=None,
            strength=Decimal("0.50"),
            timestamp_ms=1,
            reason="invalid missing side",
        )

    with pytest.raises(ValueError, match="below entry_price"):
        SizingInput(
            symbol="BTC/USDT",
            side=TradeSide.LONG,
            equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
            entry_price=Decimal("100"),
            stop_price=Decimal("100"),
            max_position_value=Decimal("1000"),
        )


def test_snapshot_rejects_mismatched_outputs() -> None:
    mismatched_entry = EntrySignal(
        symbol="ETH/USDT",
        timeframe="4h",
        action=EntryDecision.ENTER,
        side=TradeSide.LONG,
        strength=Decimal("0.70"),
        timestamp_ms=1_700_000_000_000,
        reason="wrong symbol",
    )

    with pytest.raises(ValueError, match="entry and exit symbols"):
        StrategySnapshot(
            symbol="BTC/USDT",
            timeframe="4h",
            timestamp_ms=1_700_000_000_000,
            config_hash="config-sha256",
            regime=regime(),
            entry=mismatched_entry,
            exit=exit_signal(),
            sizing_input=None,
            position_size=None,
            stop_plan=None,
        )


def test_protocol_shape_can_be_used_by_pure_strategy_components() -> None:
    class FixedClassifier:
        def classify(
            self,
            series: MarketSeries,
            context: StrategyContext,
        ) -> RegimeAssessment:
            assert series.symbol == "BTC/USDT"
            assert context.config_hash == "config-sha256"
            return regime()

    class FixedSnapshotBuilder:
        def build_snapshot(
            self,
            series: MarketSeries,
            context: StrategyContext,
        ) -> StrategySnapshot:
            assessment = FixedClassifier().classify(series, context)
            return StrategySnapshot(
                symbol=series.symbol,
                timeframe=series.timeframe,
                timestamp_ms=context.as_of_ms,
                config_hash=context.config_hash,
                regime=assessment,
                entry=entry_signal(),
                exit=exit_signal(),
                sizing_input=sizing_input(),
                position_size=position_size(),
                stop_plan=stop_plan(),
            )

    series = MarketSeries(symbol="BTC/USDT", timeframe="4h", candles=[candle()])
    snapshot = FixedSnapshotBuilder().build_snapshot(series, strategy_context())

    assert snapshot == FixedSnapshotBuilder().build_snapshot(series, strategy_context())
    assert snapshot.entry.action is EntryDecision.ENTER
