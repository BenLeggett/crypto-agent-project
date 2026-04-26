from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

import pytest

import scripts.run_freqtrade_backtest as backtest_script
import scripts.run_freqtrade_dryrun as dryrun_script
from apps.research.freqtrade_commands import (
    FreqtradeBacktestCommandRequest,
    FreqtradeCommandError,
    FreqtradeCommandResult,
    FreqtradeDryRunCommandRequest,
    build_freqtrade_backtest_command,
    build_freqtrade_dry_run_command,
    run_freqtrade_backtest,
)


class FakeRunner:
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: Sequence[str], *, cwd: Optional[Path] = None) -> FreqtradeCommandResult:
        assert cwd is None
        self.commands.append(tuple(command))
        return FreqtradeCommandResult(tuple(command), self.returncode, self.stdout, self.stderr)


def test_build_backtest_command_uses_dry_run_config_and_strategy_class() -> None:
    command = build_freqtrade_backtest_command(
        FreqtradeBacktestCommandRequest(
            timerange="20240101-20240201",
            timeframe="4h",
            export_filename=Path("data/summaries/backtest.json"),
        )
    )

    assert command[:2] == ("freqtrade", "backtesting")
    assert str(Path("freqtrade/user_data/config.dryrun.json")) in command
    assert "RegimeBreakoutStrategy" in command
    assert "--export" in command
    assert "--export-filename" in command


def test_build_dry_run_command_refuses_live_config() -> None:
    command = build_freqtrade_dry_run_command(FreqtradeDryRunCommandRequest())

    assert command[:2] == ("freqtrade", "trade")
    assert str(Path("freqtrade/user_data/config.dryrun.json")) in command
    assert "RegimeBreakoutStrategy" in command

    with pytest.raises(ValueError, match="live config"):
        FreqtradeDryRunCommandRequest(config_path=Path("freqtrade/user_data/config.live.json"))
    with pytest.raises(ValueError, match="live config"):
        FreqtradeBacktestCommandRequest(config_path=Path("configs/live/freqtrade.json"))


def test_run_backtest_raises_clear_error_on_command_failure() -> None:
    runner = FakeRunner(returncode=2, stderr="bad config")

    with pytest.raises(FreqtradeCommandError, match="bad config"):
        run_freqtrade_backtest(FreqtradeBacktestCommandRequest(), runner=runner)


def test_freqtrade_config_templates_preserve_paper_first_gates() -> None:
    dry_run = _load_json(Path("freqtrade/user_data/config.dryrun.json"))
    live = _load_json(Path("freqtrade/user_data/config.live.json"))
    project_live = _load_json(Path("configs/live/freqtrade.json"))

    assert dry_run["dry_run"] is True
    assert dry_run["strategy"] == "RegimeBreakoutStrategy"
    assert dry_run["telegram"]["enabled"] is False
    assert dry_run["api_server"]["enabled"] is False
    assert live["dry_run"] is False
    assert live["initial_state"] == "stopped"
    assert live["project_live_guardrails"]["live_execution_enabled"] is False
    assert live["project_live_guardrails"]["requires_promotion_marker"] is True
    assert live["exchange"]["key"] == "${EXCHANGE_API_KEY}"
    assert project_live["requires_human_signoff"] is True


def test_backtest_script_parses_args_and_reports_command(monkeypatch, capsys) -> None:
    captured = {}

    def fake_run_freqtrade_backtest(request):
        captured["request"] = request
        return FreqtradeCommandResult(("freqtrade", "backtesting"), 0)

    monkeypatch.setattr(backtest_script, "run_freqtrade_backtest", fake_run_freqtrade_backtest)

    exit_code = backtest_script.main(["--timerange", "20240101-", "--timeframe", "4h"])

    assert exit_code == 0
    assert captured["request"].timerange == "20240101-"
    assert captured["request"].timeframe == "4h"
    assert "backtesting" in capsys.readouterr().out


def test_dryrun_script_rejects_live_config(monkeypatch, capsys) -> None:
    called = False

    def fake_run_freqtrade_dry_run(request):
        nonlocal called
        called = True
        return FreqtradeCommandResult(("freqtrade", "trade"), 0)

    monkeypatch.setattr(dryrun_script, "run_freqtrade_dry_run", fake_run_freqtrade_dry_run)

    exit_code = dryrun_script.main(["--config", "freqtrade/user_data/config.live.json"])

    assert exit_code == 1
    assert called is False
    assert "live config" in capsys.readouterr().err


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))
