from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

from libs.strategy.breakout import BreakoutSignalConfig, BreakoutSignalGenerator
from libs.strategy.interfaces import (
    Candle,
    EntryDecision,
    MarketSeries,
    RegimeLabel,
    StrategyContext,
)
from libs.strategy.regime import DailyRegimeClassifier, RegimeFilterConfig
from libs.strategy.signal_snapshot import (
    DeterministicSignalSnapshotBuilder,
    SignalSnapshotSizingConfig,
    serialize_strategy_snapshot,
)
from libs.strategy.sizing import DeterministicPositionSizer, PositionSizingConfig
from libs.strategy.stops import RangeStopPlanner, StopPlanConfig
from libs.strategy.universe import (
    SymbolMarketInfo,
    UniverseSelectionConfig,
    select_universe,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "market_data"


def test_strategy_pipeline_is_deterministic_from_fixed_market_fixtures() -> None:
    daily_series = load_series("btc_usdt_1d_bull_regime.json")
    breakout_series = load_series("btc_usdt_4h_breakout.json")
    context = StrategyContext(
        run_id="fixture-run-001",
        config_hash="fixture-config-sha256",
        as_of_ms=breakout_series.candles[-1].timestamp_ms,
    )

    universe = select_universe(
        UniverseSelectionConfig(
            configured_symbols=("BTC/USDT", "ETH/USDT", "BTC/USDT"),
            allowed_quote_assets=("USDT",),
            denied_symbols=("ETH/USDT",),
            require_metadata=True,
            min_notional_floor=Decimal("10"),
        ),
        market_info={
            "BTC/USDT": SymbolMarketInfo(
                symbol="BTC/USDT",
                base_asset="BTC",
                quote_asset="USDT",
                is_active=True,
                min_notional=Decimal("25"),
            ),
            "ETH/USDT": SymbolMarketInfo(
                symbol="ETH/USDT",
                base_asset="ETH",
                quote_asset="USDT",
                is_active=True,
                min_notional=Decimal("25"),
            ),
        },
    )
    assert universe.selected_symbols == ("BTC/USDT",)
    assert [rejection.reason.value for rejection in universe.rejected_symbols] == [
        "denylisted",
        "duplicate_symbol",
    ]

    regime_classifier = DailyRegimeClassifier(
        RegimeFilterConfig(
            fast_ma_period=3,
            slow_ma_period=5,
            slope_period=2,
            trend_threshold=Decimal("0.02"),
            range_threshold=Decimal("0.005"),
        )
    )
    regime_context = StrategyContext(
        run_id=context.run_id,
        config_hash=context.config_hash,
        as_of_ms=daily_series.candles[-1].timestamp_ms,
    )
    first_regime = regime_classifier.classify(daily_series, regime_context)
    second_regime = regime_classifier.classify(daily_series, regime_context)
    assert first_regime == second_regime
    assert first_regime.label is RegimeLabel.BULL

    builder = DeterministicSignalSnapshotBuilder(
        regime_classifier=FixedRegimeClassifier(first_regime),
        entry_generator=BreakoutSignalGenerator(
            BreakoutSignalConfig(
                lookback_period=3,
                momentum_period=2,
                breakout_buffer=Decimal("0.01"),
                breakdown_buffer=Decimal("0.01"),
                minimum_momentum=Decimal("0.01"),
            )
        ),
        exit_generator=BreakoutSignalGenerator(
            BreakoutSignalConfig(
                lookback_period=3,
                momentum_period=2,
                breakout_buffer=Decimal("0.01"),
                breakdown_buffer=Decimal("0.01"),
                minimum_momentum=Decimal("0.01"),
            )
        ),
        stop_planner=RangeStopPlanner(
            StopPlanConfig(
                lookback_period=3,
                stop_buffer=Decimal("0.001"),
                min_stop_distance=Decimal("0.01"),
                max_stop_distance=Decimal("0.05"),
                take_profit_multiple=Decimal("2"),
            )
        ),
        position_sizer=DeterministicPositionSizer(
            PositionSizingConfig(quantity_step=Decimal("0.001"))
        ),
        sizing_config=SignalSnapshotSizingConfig(
            equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
            max_position_value=Decimal("5000"),
        ),
    )

    first_snapshot = serialize_strategy_snapshot(builder.build_snapshot(breakout_series, context))
    second_snapshot = serialize_strategy_snapshot(builder.build_snapshot(breakout_series, context))

    assert first_snapshot == second_snapshot
    assert first_snapshot["regime"]["label"] == "bull"
    assert first_snapshot["entry"]["action"] == EntryDecision.ENTER.value
    assert first_snapshot["entry"]["side"] == "long"
    assert first_snapshot["entry"]["metadata"]["prior_high"] == "102.0000"
    assert first_snapshot["stop_plan"]["stop_price"] == "100.899"
    assert first_snapshot["sizing_input"]["entry_price"] == "105"
    assert Decimal(first_snapshot["position_size"]["quantity"]) > Decimal("0")


class FixedRegimeClassifier:
    def __init__(self, regime: Any) -> None:
        self.regime = regime

    def classify(self, series: MarketSeries, context: StrategyContext) -> Any:
        return self.regime


def load_series(filename: str) -> MarketSeries:
    payload = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
    return MarketSeries(
        symbol=payload["symbol"],
        timeframe=payload["timeframe"],
        candles=tuple(
            Candle(
                symbol=payload["symbol"],
                timeframe=payload["timeframe"],
                timestamp_ms=item["timestamp_ms"],
                open=Decimal(item["open"]),
                high=Decimal(item["high"]),
                low=Decimal(item["low"]),
                close=Decimal(item["close"]),
                volume=Decimal(item["volume"]),
            )
            for item in payload["candles"]
        ),
    )
