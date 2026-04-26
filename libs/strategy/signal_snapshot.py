"""Canonical deterministic signal snapshot schema and builder."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping, Optional

from libs.strategy.breakout import BreakoutSignalGenerator
from libs.strategy.interfaces import (
    EntryDecision,
    EntrySignal,
    EntrySignalGenerator,
    ExitSignal,
    ExitSignalGenerator,
    MarketSeries,
    PositionSize,
    PositionSizer,
    RegimeAssessment,
    RegimeClassifier,
    SizingInput,
    StopPlan,
    StopPlanner,
    StrategyContext,
    StrategySnapshot,
)
from libs.strategy.regime import DailyRegimeClassifier
from libs.strategy.sizing import DeterministicPositionSizer
from libs.strategy.stops import RangeStopPlanner

SNAPSHOT_SCHEMA_VERSION = "strategy_snapshot.v1"


@dataclass(frozen=True)
class SignalSnapshotSizingConfig:
    """Config values needed to derive sizing input from a stop plan."""

    equity: Decimal
    risk_fraction: Decimal
    max_position_value: Decimal

    def __post_init__(self) -> None:
        _require_positive_decimal(self.equity, "equity")
        _require_ratio(self.risk_fraction, "risk_fraction")
        _require_positive_decimal(self.max_position_value, "max_position_value")


class DeterministicSignalSnapshotBuilder:
    """Build a replayable deterministic strategy snapshot from pure components."""

    def __init__(
        self,
        regime_classifier: Optional[RegimeClassifier] = None,
        entry_generator: Optional[EntrySignalGenerator] = None,
        exit_generator: Optional[ExitSignalGenerator] = None,
        stop_planner: Optional[StopPlanner] = None,
        position_sizer: Optional[PositionSizer] = None,
        sizing_config: Optional[SignalSnapshotSizingConfig] = None,
    ) -> None:
        self.regime_classifier = regime_classifier or DailyRegimeClassifier()
        self.entry_generator = entry_generator or BreakoutSignalGenerator()
        self.exit_generator = exit_generator or BreakoutSignalGenerator()
        self.stop_planner = stop_planner or RangeStopPlanner()
        self.position_sizer = position_sizer or DeterministicPositionSizer()
        self.sizing_config = sizing_config

    def build_snapshot(self, series: MarketSeries, context: StrategyContext) -> StrategySnapshot:
        regime = self.regime_classifier.classify(series, context)
        entry = self.entry_generator.generate_entry(series, regime, context)
        exit_signal = self.exit_generator.generate_exit(series, regime, context)
        stop_plan = self.stop_planner.plan_stop(series, entry, context)
        sizing_input = self._build_sizing_input(series, entry, stop_plan)
        position_size = (
            self.position_sizer.size(sizing_input, context) if sizing_input is not None else None
        )

        return StrategySnapshot(
            symbol=series.symbol,
            timeframe=series.timeframe,
            timestamp_ms=context.as_of_ms,
            config_hash=context.config_hash,
            regime=regime,
            entry=entry,
            exit=exit_signal,
            sizing_input=sizing_input,
            position_size=position_size,
            stop_plan=stop_plan,
            metadata={
                "schema_version": SNAPSHOT_SCHEMA_VERSION,
                "run_id": context.run_id,
                "latest_close": _decimal(series.candles[-1].close),
                "candle_count": str(len(series.candles)),
            },
        )

    def _build_sizing_input(
        self,
        series: MarketSeries,
        entry: EntrySignal,
        stop_plan: Optional[StopPlan],
    ) -> Optional[SizingInput]:
        if entry.action is not EntryDecision.ENTER:
            return None
        if entry.side is None:
            raise ValueError("entry side is required for sizing")
        if stop_plan is None:
            raise ValueError("stop plan is required for entry sizing")
        if self.sizing_config is None:
            raise ValueError("sizing_config is required when entry action is ENTER")

        return SizingInput(
            symbol=series.symbol,
            side=entry.side,
            equity=self.sizing_config.equity,
            risk_fraction=self.sizing_config.risk_fraction,
            entry_price=_entry_price(entry, series.candles[-1].close),
            stop_price=stop_plan.stop_price,
            max_position_value=self.sizing_config.max_position_value,
        )


def build_signal_snapshot(
    series: MarketSeries,
    context: StrategyContext,
    sizing_config: Optional[SignalSnapshotSizingConfig] = None,
    regime_classifier: Optional[RegimeClassifier] = None,
    entry_generator: Optional[EntrySignalGenerator] = None,
    exit_generator: Optional[ExitSignalGenerator] = None,
    stop_planner: Optional[StopPlanner] = None,
    position_sizer: Optional[PositionSizer] = None,
) -> StrategySnapshot:
    """Convenience wrapper around `DeterministicSignalSnapshotBuilder`."""
    return DeterministicSignalSnapshotBuilder(
        regime_classifier=regime_classifier,
        entry_generator=entry_generator,
        exit_generator=exit_generator,
        stop_planner=stop_planner,
        position_sizer=position_sizer,
        sizing_config=sizing_config,
    ).build_snapshot(series, context)


def serialize_strategy_snapshot(snapshot: StrategySnapshot) -> dict[str, Any]:
    """Return the canonical machine-readable v1 snapshot shape."""
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "symbol": snapshot.symbol,
        "timeframe": snapshot.timeframe,
        "timestamp_ms": snapshot.timestamp_ms,
        "config_hash": snapshot.config_hash,
        "regime": _regime_to_dict(snapshot.regime),
        "entry": _entry_to_dict(snapshot.entry),
        "exit": _exit_to_dict(snapshot.exit),
        "sizing_input": _sizing_input_to_dict(snapshot.sizing_input),
        "position_size": _position_size_to_dict(snapshot.position_size),
        "stop_plan": _stop_plan_to_dict(snapshot.stop_plan),
        "metadata": dict(snapshot.metadata),
    }


def _regime_to_dict(regime: RegimeAssessment) -> dict[str, Any]:
    return {
        "label": regime.label.value,
        "confidence": _decimal(regime.confidence),
        "as_of_ms": regime.as_of_ms,
        "reason": regime.reason,
        "metadata": dict(regime.metadata),
    }


def _entry_to_dict(entry: EntrySignal) -> dict[str, Any]:
    return {
        "action": entry.action.value,
        "side": entry.side.value if entry.side is not None else None,
        "strength": _decimal(entry.strength),
        "timestamp_ms": entry.timestamp_ms,
        "reason": entry.reason,
        "metadata": dict(entry.metadata),
    }


def _exit_to_dict(exit_signal: ExitSignal) -> dict[str, Any]:
    return {
        "action": exit_signal.action.value,
        "side": exit_signal.side.value if exit_signal.side is not None else None,
        "strength": _decimal(exit_signal.strength),
        "timestamp_ms": exit_signal.timestamp_ms,
        "reason": exit_signal.reason,
        "metadata": dict(exit_signal.metadata),
    }


def _sizing_input_to_dict(sizing_input: Optional[SizingInput]) -> Optional[dict[str, Any]]:
    if sizing_input is None:
        return None
    return {
        "symbol": sizing_input.symbol,
        "side": sizing_input.side.value,
        "equity": _decimal(sizing_input.equity),
        "risk_fraction": _decimal(sizing_input.risk_fraction),
        "entry_price": _decimal(sizing_input.entry_price),
        "stop_price": _decimal(sizing_input.stop_price),
        "max_position_value": _decimal(sizing_input.max_position_value),
    }


def _position_size_to_dict(position_size: Optional[PositionSize]) -> Optional[dict[str, Any]]:
    if position_size is None:
        return None
    return {
        "symbol": position_size.symbol,
        "side": position_size.side.value,
        "quantity": _decimal(position_size.quantity),
        "notional": _decimal(position_size.notional),
        "risk_amount": _decimal(position_size.risk_amount),
        "reason": position_size.reason,
        "metadata": dict(position_size.metadata),
    }


def _stop_plan_to_dict(stop_plan: Optional[StopPlan]) -> Optional[dict[str, Any]]:
    if stop_plan is None:
        return None
    return {
        "symbol": stop_plan.symbol,
        "side": stop_plan.side.value,
        "stop_price": _decimal(stop_plan.stop_price),
        "take_profit_price": _decimal(stop_plan.take_profit_price) if stop_plan.take_profit_price is not None else None,
        "trailing_distance": _decimal(stop_plan.trailing_distance) if stop_plan.trailing_distance is not None else None,
        "reason": stop_plan.reason,
        "metadata": dict(stop_plan.metadata),
    }


def _entry_price(entry: EntrySignal, fallback_close: Decimal) -> Decimal:
    value = entry.metadata.get("latest_close") or entry.metadata.get("entry_price")
    if value is None:
        return fallback_close
    try:
        price = Decimal(value)
    except Exception as exc:
        raise ValueError("entry metadata price must be Decimal-compatible") from exc
    if price <= Decimal("0"):
        raise ValueError("entry metadata price must be positive")
    return price


def _decimal(value: Decimal) -> str:
    return str(value.normalize())


def _require_positive_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value <= Decimal("0"):
        raise ValueError(f"{field_name} must be positive")


def _require_ratio(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value < Decimal("0") or value > Decimal("1"):
        raise ValueError(f"{field_name} must be between 0 and 1")


__all__ = [
    "DeterministicSignalSnapshotBuilder",
    "SNAPSHOT_SCHEMA_VERSION",
    "SignalSnapshotSizingConfig",
    "build_signal_snapshot",
    "serialize_strategy_snapshot",
]
