from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.research.walkforward import (
    WALK_FORWARD_SCHEMA_VERSION,
    WalkForwardSplit,
    parse_split_spec,
    run_walk_forward_evaluation,
)
from scripts import run_walkforward


def _write_backtest(path: Path, *, profit: str, trades: int, drawdown: str) -> None:
    payload = {
        "strategy": {
            "regime_breakout_strategy": {
                "backtest_start": "2024-01-01 00:00:00",
                "backtest_end": "2024-02-01 00:00:00",
                "total_trades": trades,
                "wins": trades - 1,
                "losses": 1,
                "profit_total": profit,
                "max_drawdown_account": drawdown,
            }
        }
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_walk_forward_runner_writes_manifest_split_metadata_and_metrics(tmp_path: Path) -> None:
    first = tmp_path / "fold1.json"
    second = tmp_path / "fold2.json"
    _write_backtest(first, profit="0.10", trades=4, drawdown="0.02")
    _write_backtest(second, profit="0.20", trades=6, drawdown="0.03")

    run, manifest_path = run_walk_forward_evaluation(
        splits=(
            WalkForwardSplit("fold1", "2024-01-01", "2024-01-31", "2024-02-01", "2024-02-29", first),
            WalkForwardSplit("fold2", "2024-03-01", "2024-03-31", "2024-04-01", "2024-04-30", second),
        ),
        output_dir=tmp_path / "runs",
        run_id="wf_fixture",
        generated_at="2026-04-26T00:00:00+00:00",
    )

    saved = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert run.schema_version == WALK_FORWARD_SCHEMA_VERSION
    assert manifest_path == tmp_path / "runs" / "wf_fixture" / "walk_forward_run.json"
    assert saved["schema_version"] == WALK_FORWARD_SCHEMA_VERSION
    assert saved["split_count"] == 2
    assert saved["split_results"][0]["split_id"] == "fold1"
    assert saved["split_results"][0]["metrics_artifact_path"].startswith("metrics")
    assert saved["aggregate_metrics"]["avg_profit_total_ratio"] == "0.15"
    assert saved["aggregate_metrics"]["worst_max_drawdown_ratio"] == "0.03"
    assert saved["aggregate_metrics"]["total_trades"] == "10"
    assert len(tuple((tmp_path / "runs" / "wf_fixture" / "metrics").glob("*.json"))) == 2


def test_split_validation_rejects_overlapping_train_and_test_windows(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="train_end"):
        WalkForwardSplit("bad", "2024-01-01", "2024-02-15", "2024-02-01", "2024-02-29", tmp_path / "x.json")


def test_split_validation_rejects_invalid_date_values(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="invalid date value"):
        WalkForwardSplit("bad", "2024-01-01", "not-a-date", "2024-02-01", "2024-02-29", tmp_path / "x.json")


def test_parse_split_spec_builds_typed_split() -> None:
    split = parse_split_spec("fold1,results.json,20240101,20240131,20240201,20240229")

    assert split.split_id == "fold1"
    assert split.backtest_result_path == Path("results.json")
    assert split.train_start == "20240101"
    assert split.test_end == "20240229"


def test_run_walkforward_cli_writes_manifest_for_split_specs(tmp_path: Path) -> None:
    source = tmp_path / "fold1.json"
    _write_backtest(source, profit="0.10", trades=4, drawdown="0.02")

    exit_code = run_walkforward.main(
        [
            "--split",
            f"fold1,{source},2024-01-01,2024-01-31,2024-02-01,2024-02-29",
            "--output-dir",
            str(tmp_path / "runs"),
            "--run-id",
            "wf_cli",
        ]
    )

    assert exit_code == 0
    assert (tmp_path / "runs" / "wf_cli" / "walk_forward_run.json").is_file()
