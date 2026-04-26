from __future__ import annotations

import json
from pathlib import Path

from apps.research.reports import summarize_freqtrade_backtest
from apps.research.walkforward import WalkForwardSplit, run_walk_forward_evaluation


def _write_backtest(path: Path, *, profit: str, trades: tuple[str, ...], drawdown: str) -> None:
    payload = {
        "strategy": {
            "regime_breakout_strategy": {
                "backtest_start": "2024-01-01 00:00:00",
                "backtest_end": "2024-02-01 00:00:00",
                "profit_total": profit,
                "max_drawdown_account": drawdown,
                "trades": [{"profit_ratio": value} for value in trades],
            }
        }
    }
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def test_research_metric_calculation_is_reproducible_from_fixed_backtest_payload() -> None:
    payload = {
        "strategy": {
            "regime_breakout_strategy": {
                "profit_total": "0.075",
                "profit_total_abs": "18.25",
                "max_drawdown_account": "0.0225",
                "trades": [
                    {"profit_ratio": "0.02"},
                    {"profit_ratio": "-0.01"},
                    {"profit_ratio": "0.03"},
                    {"profit_ratio": "0"},
                ],
            }
        }
    }

    first = summarize_freqtrade_backtest(
        payload,
        source_path=Path("fixed-backtest.json"),
        generated_at="2026-04-26T00:00:00+00:00",
    ).to_record()
    second = summarize_freqtrade_backtest(
        payload,
        source_path=Path("fixed-backtest.json"),
        generated_at="2026-04-26T00:00:00+00:00",
    ).to_record()

    metrics = {metric["name"]: metric["value"] for metric in first["metrics"]}
    assert first == second
    assert metrics == {
        "losing_trades": "1",
        "max_drawdown_ratio": "0.0225",
        "profit_total_abs": "18.25",
        "profit_total_ratio": "0.075",
        "total_trades": "4",
        "win_rate": "0.5",
        "winning_trades": "2",
    }
    assert first["notes"] == "Backtest evidence only; not live approval."


def test_walk_forward_manifest_is_reproducible_from_fixed_split_inputs(tmp_path: Path) -> None:
    first = tmp_path / "fold1.json"
    second = tmp_path / "fold2.json"
    _write_backtest(first, profit="0.10", trades=("0.02", "-0.01", "0.03"), drawdown="0.02")
    _write_backtest(second, profit="-0.04", trades=("-0.02", "0.01"), drawdown="0.05")

    splits = (
        WalkForwardSplit("fold1", "2024-01-01", "2024-01-31", "2024-02-01", "2024-02-29", first),
        WalkForwardSplit("fold2", "2024-03-01", "2024-03-31", "2024-04-01", "2024-04-30", second),
    )
    kwargs = {
        "splits": splits,
        "output_dir": tmp_path / "research",
        "run_id": "wf_regression",
        "generated_at": "2026-04-26T00:00:00+00:00",
    }

    _, first_manifest_path = run_walk_forward_evaluation(**kwargs)
    first_manifest = json.loads(first_manifest_path.read_text(encoding="utf-8"))
    _, second_manifest_path = run_walk_forward_evaluation(**kwargs)
    second_manifest = json.loads(second_manifest_path.read_text(encoding="utf-8"))

    assert first_manifest == second_manifest
    assert first_manifest["aggregate_metrics"] == {
        "avg_max_drawdown_ratio": "0.035",
        "avg_profit_total_ratio": "0.03",
        "avg_trades_per_split": "2.5",
        "max_profit_total_ratio": "0.1",
        "min_profit_total_ratio": "-0.04",
        "split_count": "2",
        "total_trades": "5",
        "worst_max_drawdown_ratio": "0.05",
    }
    assert first_manifest["notes"] == "Walk-forward evidence only; not live approval."
