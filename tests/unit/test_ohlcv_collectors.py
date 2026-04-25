from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

import pytest

import scripts.bootstrap_data as bootstrap_script
import scripts.update_market_data as update_script
from apps.collector.jobs import bootstrap_ohlcv, update_ohlcv
from libs.config import load_config
from libs.market_data.collectors import (
    CommandResult,
    MarketDataCollectorError,
    OHLCVCollectionRequest,
    build_freqtrade_download_command,
    run_freqtrade_ohlcv_download,
)


class FakeRunner:
    def __init__(self, returncode: int = 0, stdout: str = "ok", stderr: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.commands: list[tuple[str, ...]] = []

    def run(self, command: Sequence[str], *, cwd: Optional[Path] = None) -> CommandResult:
        assert cwd is None
        self.commands.append(tuple(command))
        return CommandResult(tuple(command), self.returncode, self.stdout, self.stderr)


def test_build_freqtrade_download_command_for_bootstrap() -> None:
    request = OHLCVCollectionRequest(
        symbols=("BTC/USDT", "ETH/USDT"),
        timeframes=("1h", "4h"),
        exchange="binance",
        timerange="20240101-20240201",
    )

    command = build_freqtrade_download_command(request)

    assert command == (
        "freqtrade",
        "download-data",
        "--config",
        str(Path("configs/dry_run/freqtrade.json")),
        "--userdir",
        str(Path("freqtrade/user_data")),
        "--trading-mode",
        "spot",
        "--pairs",
        "BTC/USDT",
        "ETH/USDT",
        "--timeframes",
        "1h",
        "4h",
        "--exchange",
        "binance",
        "--timerange",
        "20240101-20240201",
    )


def test_update_job_uses_config_symbols_and_days() -> None:
    config = load_config(environ={"SYMBOLS": "BTC/USDT,ETH/USDT", "TIMEFRAMES": "1h"})
    runner = FakeRunner()

    result = update_ohlcv(config=config, days=3, runner=runner)

    assert result.provider == "freqtrade"
    assert runner.commands[0][-2:] == ("--days", "3")
    assert "--pairs" in runner.commands[0]
    assert "BTC/USDT" in runner.commands[0]
    assert "ETH/USDT" in runner.commands[0]


def test_bootstrap_job_allows_cli_overrides() -> None:
    config = load_config(environ={"SYMBOLS": "BTC/USDT", "TIMEFRAMES": "1h"})
    runner = FakeRunner()

    result = bootstrap_ohlcv(
        config=config,
        symbols=("SOL/USDT",),
        timeframes=("15m",),
        timerange="20240101-",
        freqtrade_command="freqtrade-local",
        runner=runner,
    )

    assert result.command[0] == "freqtrade-local"
    assert "SOL/USDT" in result.command
    assert "15m" in result.command
    assert result.command[-2:] == ("--timerange", "20240101-")


def test_collection_failure_raises_clear_error() -> None:
    request = OHLCVCollectionRequest(symbols=("BTC/USDT",), timeframes=("1h",))
    runner = FakeRunner(returncode=2, stderr="bad config")

    with pytest.raises(MarketDataCollectorError, match="bad config"):
        run_freqtrade_ohlcv_download(request, operation="bootstrap", runner=runner)


def test_request_requires_symbols_and_timeframes() -> None:
    with pytest.raises(ValueError, match="at least one symbol"):
        OHLCVCollectionRequest(symbols=(), timeframes=("1h",))
    with pytest.raises(ValueError, match="at least one timeframe"):
        OHLCVCollectionRequest(symbols=("BTC/USDT",), timeframes=())


def test_bootstrap_script_parses_args_and_reports_command(monkeypatch, capsys) -> None:
    captured = {}

    def fake_bootstrap_ohlcv(**kwargs):
        captured.update(kwargs)
        return type(
            "Result",
            (),
            {"provider": "freqtrade", "command": ("freqtrade", "download-data")},
        )()

    monkeypatch.setattr(bootstrap_script, "bootstrap_ohlcv", fake_bootstrap_ohlcv)

    exit_code = bootstrap_script.main(
        ["--symbols", "BTC/USDT,ETH/USDT", "--timeframes", "1h", "--exchange", "binance"]
    )

    assert exit_code == 0
    assert captured["symbols"] == ("BTC/USDT", "ETH/USDT")
    assert captured["timeframes"] == ("1h",)
    assert captured["exchange"] == "binance"
    assert "download-data" in capsys.readouterr().out


def test_update_script_parses_days(monkeypatch) -> None:
    captured = {}

    def fake_update_ohlcv(**kwargs):
        captured.update(kwargs)
        return type(
            "Result",
            (),
            {"provider": "freqtrade", "command": ("freqtrade", "download-data", "--days", "2")},
        )()

    monkeypatch.setattr(update_script, "update_ohlcv", fake_update_ohlcv)

    exit_code = update_script.main(["--symbols", "BTC/USDT", "--timeframes", "1h", "--days", "2"])

    assert exit_code == 0
    assert captured["days"] == 2
