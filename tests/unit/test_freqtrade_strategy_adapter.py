from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

pd = pytest.importorskip("pandas")

from freqtrade.user_data.strategies.regime_breakout_strategy import (
    RegimeBreakoutAdapterConfig,
    RegimeBreakoutStrategy,
    latest_decision_from_dataframe,
    market_series_from_records,
)
from libs.decisioning.schemas import DecisionMode, TradeProposal


def test_market_series_conversion_uses_shared_contract() -> None:
    records = [
        {
            "date": "2026-01-01T00:00:00+00:00",
            "open": "100",
            "high": "101",
            "low": "99",
            "close": "100.5",
            "volume": "12",
        }
    ]

    series = market_series_from_records(symbol="BTC/USDT", timeframe="4h", records=records)

    assert series.symbol == "BTC/USDT"
    assert series.candles[0].timestamp_ms == 1_767_225_600_000
    assert series.candles[0].close == Decimal("100.5")


def test_latest_decision_from_dataframe_uses_shared_decision_schema() -> None:
    dataframe = _breakout_dataframe()

    result = latest_decision_from_dataframe(
        dataframe,
        pair="BTC/USDT",
        adapter_config=RegimeBreakoutAdapterConfig(allowed_symbols=("BTC/USDT",), proposal_ttl_ms=60_000),
    )

    assert result.decision_input.mode is DecisionMode.PAPER
    assert result.decision_input.strategy_snapshot is not None
    assert result.decision_input.strategy_snapshot["schema_version"] == "strategy_snapshot.v1"
    assert isinstance(result.output, TradeProposal)
    assert result.output.symbol == "BTC/USDT"
    assert "requires_supervisor_review" in result.output.risk_tags
    assert not hasattr(result.output, "place_order")


def test_populate_entry_trend_annotates_but_does_not_enable_entries_by_default() -> None:
    strategy = RegimeBreakoutStrategy()
    dataframe = _breakout_dataframe()

    annotated = strategy.populate_entry_trend(dataframe, {"pair": "BTC/USDT"})
    latest = annotated.iloc[-1]

    assert latest["ca_decision_kind"] == "proposal"
    assert latest["ca_requires_supervisor_review"] is True
    assert latest["ca_decision_record"]["output"]["schema_version"] == "trade_proposal.v1"
    assert latest["enter_long"] == 0
    assert latest["enter_short"] == 0


def test_adapter_emits_no_trade_for_out_of_universe_pair() -> None:
    result = latest_decision_from_dataframe(
        _breakout_dataframe(),
        pair="ETH/USDT",
        adapter_config=RegimeBreakoutAdapterConfig(allowed_symbols=("BTC/USDT",)),
    )

    assert result.output.to_record()["schema_version"] == "no_trade_decision.v1"
    assert result.output.to_record()["reason"] == "out_of_universe"


def _breakout_dataframe() -> "pd.DataFrame":
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    for index in range(40):
        close = Decimal("100") + Decimal(index)
        if index == 39:
            close = Decimal("150")
        open_price = close - Decimal("0.5")
        high = close + Decimal("1")
        low = close - Decimal("1")
        if index == 39:
            high = Decimal("151")
            low = Decimal("148")
        rows.append(
            {
                "date": start + timedelta(hours=4 * index),
                "open": float(open_price),
                "high": float(high),
                "low": float(low),
                "close": float(close),
                "volume": 1000.0 + index,
            }
        )
    return pd.DataFrame(rows)
