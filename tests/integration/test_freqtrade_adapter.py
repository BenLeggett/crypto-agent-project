from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Optional, Sequence

import pytest

pd = pytest.importorskip("pandas")

from apps.research.freqtrade_commands import (
    FreqtradeBacktestCommandRequest,
    FreqtradeCommandResult,
    FreqtradeDryRunCommandRequest,
    run_freqtrade_backtest,
    run_freqtrade_dry_run,
)
from freqtrade.user_data.strategies.regime_breakout_strategy import (
    RegimeBreakoutAdapterConfig,
    RegimeBreakoutStrategy,
    latest_decision_from_dataframe,
)


class FakeFreqtradeRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: Sequence[str], *, cwd: Optional[Path] = None) -> FreqtradeCommandResult:
        assert cwd is None
        self.commands.append(tuple(command))
        return FreqtradeCommandResult(tuple(command), 0, stdout="ok")


def test_adapter_indicator_output_matches_direct_shared_decision_path() -> None:
    dataframe = _breakout_dataframe()
    strategy = RegimeBreakoutStrategy()
    strategy.adapter_config = RegimeBreakoutAdapterConfig(
        allowed_symbols=("BTC/USDT",),
        proposal_ttl_ms=60_000,
    )

    direct = latest_decision_from_dataframe(
        dataframe,
        pair="BTC/USDT",
        adapter_config=strategy.adapter_config,
    )
    annotated = strategy.populate_indicators(dataframe.copy(), {"pair": "BTC/USDT"})
    latest = annotated.iloc[-1]

    assert latest["ca_decision_record"] == direct.to_record()
    assert latest["ca_decision_kind"] == "proposal"
    assert latest["ca_requires_supervisor_review"] is True
    assert latest["ca_decision_record"]["decision_input"]["strategy_snapshot"]["schema_version"] == "strategy_snapshot.v1"
    assert latest["ca_decision_record"]["output"]["schema_version"] == "trade_proposal.v1"


def test_adapter_entry_hook_keeps_freqtrade_entries_disabled_until_risk_wiring() -> None:
    strategy = RegimeBreakoutStrategy()
    strategy.adapter_config = RegimeBreakoutAdapterConfig(allowed_symbols=("BTC/USDT",))

    annotated = strategy.populate_entry_trend(_breakout_dataframe(), {"pair": "BTC/USDT"})
    latest = annotated.iloc[-1]

    assert latest["ca_decision_kind"] == "proposal"
    assert latest["enter_long"] == 0
    assert latest["enter_short"] == 0
    assert latest["enter_tag"] == ""


def test_backtest_and_dry_run_wrappers_smoke_with_fake_runner() -> None:
    runner = FakeFreqtradeRunner()

    backtest = run_freqtrade_backtest(
        FreqtradeBacktestCommandRequest(
            timerange="20260101-20260201",
            timeframe="4h",
            export_filename=Path("data/summaries/freqtrade-backtest.json"),
        ),
        runner=runner,
    )
    dry_run = run_freqtrade_dry_run(FreqtradeDryRunCommandRequest(), runner=runner)

    assert backtest.command[:2] == ("freqtrade", "backtesting")
    assert dry_run.command[:2] == ("freqtrade", "trade")
    assert all(str(Path("freqtrade/user_data/config.dryrun.json")) in command for command in runner.commands)
    assert all("RegimeBreakoutStrategy" in command for command in runner.commands)


def test_freqtrade_templates_keep_live_execution_gated_and_unwired() -> None:
    dry_run = _load_json(Path("freqtrade/user_data/config.dryrun.json"))
    live = _load_json(Path("freqtrade/user_data/config.live.json"))

    assert dry_run["dry_run"] is True
    assert dry_run["telegram"]["enabled"] is False
    assert dry_run["api_server"]["enabled"] is False
    assert live["dry_run"] is False
    assert live["initial_state"] == "stopped"
    assert live["exchange"]["key"] == "${EXCHANGE_API_KEY}"
    assert live["project_live_guardrails"] == {
        "live_execution_enabled": False,
        "requires_promotion_marker": True,
        "requires_human_signoff": True,
        "notes": "Template only. Do not use for live trading until promotion gates and manual wiring are complete.",
    }

    with pytest.raises(ValueError, match="live config"):
        FreqtradeDryRunCommandRequest(config_path=Path("freqtrade/user_data/config.live.json"))
    with pytest.raises(ValueError, match="live config"):
        FreqtradeBacktestCommandRequest(config_path=Path("configs/live/freqtrade.json"))


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


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
