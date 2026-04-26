from __future__ import annotations

import json
from pathlib import Path

from apps.research import main as research_main
from apps.research.reports import (
    FreqtradeBacktestRequest,
    build_freqtrade_backtest_command,
    create_backtest_evaluation_artifact,
    summarize_freqtrade_backtest,
)
from scripts import run_walkforward


def _backtest_payload() -> dict:
    return {
        "strategy": {
            "regime_breakout_strategy": {
                "backtest_start": "2024-01-01 00:00:00",
                "backtest_end": "2024-03-01 00:00:00",
                "total_trades": 3,
                "wins": 2,
                "losses": 1,
                "profit_total": "0.1234",
                "profit_total_abs": "42.50",
                "max_drawdown_abs": "7.25",
                "max_drawdown_account": "0.015",
            }
        }
    }


def test_build_freqtrade_backtest_command_is_explicit_and_dry_run_based() -> None:
    command = build_freqtrade_backtest_command(
        FreqtradeBacktestRequest(
            timerange="20240101-20240301",
            timeframe="4h",
            export_filename=Path("data/summaries/backtest.json"),
        )
    )

    assert command[:2] == ("freqtrade", "backtesting")
    assert "--config" in command
    assert str(Path("freqtrade/user_data/config.dryrun.json")) in command
    assert "--strategy" in command
    assert "RegimeBreakoutStrategy" in command
    assert "--timerange" in command
    assert "--export-filename" in command


def test_summarize_freqtrade_backtest_emits_versioned_metrics() -> None:
    evaluation = summarize_freqtrade_backtest(
        _backtest_payload(),
        source_path=Path("backtest-result.json"),
        generated_at="2026-04-26T00:00:00+00:00",
    )

    metrics = {metric.name: metric.to_record() for metric in evaluation.metrics}
    assert evaluation.schema_version == "research_backtest_metrics.v1"
    assert evaluation.source_framework == "freqtrade"
    assert evaluation.strategy_name == "regime_breakout_strategy"
    assert evaluation.notes == "Backtest evidence only; not live approval."
    assert metrics["total_trades"]["value"] == "3"
    assert metrics["winning_trades"]["value"] == "2"
    assert metrics["win_rate"]["value"] == "0.6667"
    assert metrics["profit_total_ratio"]["value"] == "0.1234"


def test_create_backtest_evaluation_artifact_writes_replayable_json(tmp_path: Path) -> None:
    source = tmp_path / "freqtrade-backtest.json"
    output_dir = tmp_path / "research"
    source.write_text(json.dumps(_backtest_payload()), encoding="utf-8")

    evaluation, output_path = create_backtest_evaluation_artifact(
        backtest_result_path=source,
        output_dir=output_dir,
        variant="deterministic_baseline",
        generated_at="2026-04-26T00:00:00+00:00",
    )

    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert output_path.parent == output_dir
    assert saved["schema_version"] == evaluation.schema_version
    assert saved["variant"] == "deterministic_baseline"
    assert saved["source_sha256"] == evaluation.source_sha256
    assert saved["metrics"][0]["name"] == "losing_trades"


def test_research_main_backtest_report_cli_writes_artifact(tmp_path: Path) -> None:
    source = tmp_path / "freqtrade-backtest.json"
    output_dir = tmp_path / "research"
    source.write_text(json.dumps(_backtest_payload()), encoding="utf-8")

    exit_code = research_main.main(
        [
            "backtest-report",
            "--input",
            str(source),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert tuple(output_dir.glob("*.json"))


def test_run_walkforward_wrapper_can_emit_task_17_metrics(tmp_path: Path) -> None:
    source = tmp_path / "freqtrade-backtest.json"
    output_dir = tmp_path / "research"
    source.write_text(json.dumps(_backtest_payload()), encoding="utf-8")

    exit_code = run_walkforward.main(
        [
            "--backtest-result",
            str(source),
            "--output-dir",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    assert tuple(output_dir.glob("*.json"))
