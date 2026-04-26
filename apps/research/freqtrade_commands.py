"""Command wrappers for the selected Freqtrade foundation.

The wrappers build and run explicit Freqtrade commands without shell expansion.
They keep paper/dry-run as the default and refuse live command construction;
future live execution must go through later promotion and manual wiring gates.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Sequence


class FreqtradeCommandError(RuntimeError):
    """Raised when a Freqtrade command cannot be prepared or completed."""


@dataclass(frozen=True)
class FreqtradeCommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


class FreqtradeCommandRunner(Protocol):
    """Side-effect boundary for Freqtrade command execution."""

    def run(self, command: Sequence[str], *, cwd: Optional[Path] = None) -> FreqtradeCommandResult:
        ...


class SubprocessFreqtradeCommandRunner:
    """Run Freqtrade directly without a shell."""

    def run(self, command: Sequence[str], *, cwd: Optional[Path] = None) -> FreqtradeCommandResult:
        try:
            completed = subprocess.run(
                list(command),
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise FreqtradeCommandError(
                f"Command not found: {command[0]!r}. Install Freqtrade or pass --freqtrade-command."
            ) from exc
        return FreqtradeCommandResult(
            command=tuple(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True)
class FreqtradeBacktestCommandRequest:
    config_path: Path = Path("freqtrade/user_data/config.dryrun.json")
    user_data_dir: Path = Path("freqtrade/user_data")
    strategy: str = "RegimeBreakoutStrategy"
    command: str = "freqtrade"
    timerange: Optional[str] = None
    timeframe: Optional[str] = None
    export_filename: Optional[Path] = None

    def __post_init__(self) -> None:
        _validate_common(self.command, self.strategy, self.config_path)


@dataclass(frozen=True)
class FreqtradeDryRunCommandRequest:
    config_path: Path = Path("freqtrade/user_data/config.dryrun.json")
    user_data_dir: Path = Path("freqtrade/user_data")
    strategy: str = "RegimeBreakoutStrategy"
    command: str = "freqtrade"

    def __post_init__(self) -> None:
        _validate_common(self.command, self.strategy, self.config_path)
        if _is_live_config_path(self.config_path):
            raise ValueError("dry-run wrapper cannot use a live config path")


def build_freqtrade_backtest_command(request: FreqtradeBacktestCommandRequest) -> tuple[str, ...]:
    """Build a dry-run based Freqtrade backtesting command."""

    command = [
        request.command,
        "backtesting",
        "--config",
        str(request.config_path),
        "--userdir",
        str(request.user_data_dir),
        "--strategy",
        request.strategy,
        "--export",
        "trades",
    ]
    if request.timerange:
        command.extend(["--timerange", request.timerange])
    if request.timeframe:
        command.extend(["--timeframe", request.timeframe])
    if request.export_filename:
        command.extend(["--export-filename", str(request.export_filename)])
    return tuple(command)


def build_freqtrade_dry_run_command(request: FreqtradeDryRunCommandRequest) -> tuple[str, ...]:
    """Build a Freqtrade dry-run/paper trade command."""

    return (
        request.command,
        "trade",
        "--config",
        str(request.config_path),
        "--userdir",
        str(request.user_data_dir),
        "--strategy",
        request.strategy,
    )


def run_freqtrade_backtest(
    request: FreqtradeBacktestCommandRequest,
    *,
    runner: Optional[FreqtradeCommandRunner] = None,
    cwd: Optional[Path] = None,
) -> FreqtradeCommandResult:
    return _run(build_freqtrade_backtest_command(request), operation="backtest", runner=runner, cwd=cwd)


def run_freqtrade_dry_run(
    request: FreqtradeDryRunCommandRequest,
    *,
    runner: Optional[FreqtradeCommandRunner] = None,
    cwd: Optional[Path] = None,
) -> FreqtradeCommandResult:
    return _run(build_freqtrade_dry_run_command(request), operation="dry-run", runner=runner, cwd=cwd)


def _run(
    command: tuple[str, ...],
    *,
    operation: str,
    runner: Optional[FreqtradeCommandRunner],
    cwd: Optional[Path],
) -> FreqtradeCommandResult:
    command_runner = runner or SubprocessFreqtradeCommandRunner()
    result = command_runner.run(command, cwd=cwd)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise FreqtradeCommandError(f"Freqtrade {operation} failed with exit code {result.returncode}: {detail}")
    return result


def _validate_common(command: str, strategy: str, config_path: Path) -> None:
    if not command:
        raise ValueError("command is required")
    if not strategy:
        raise ValueError("strategy is required")
    if _is_live_config_path(config_path):
        raise ValueError("live config is not accepted by Task 25 wrappers")


def _is_live_config_path(config_path: Path) -> bool:
    parts = {part.lower() for part in config_path.parts}
    return config_path.name.lower() == "config.live.json" or "live" in parts


__all__ = [
    "FreqtradeBacktestCommandRequest",
    "FreqtradeCommandError",
    "FreqtradeCommandResult",
    "FreqtradeCommandRunner",
    "FreqtradeDryRunCommandRequest",
    "SubprocessFreqtradeCommandRunner",
    "build_freqtrade_backtest_command",
    "build_freqtrade_dry_run_command",
    "run_freqtrade_backtest",
    "run_freqtrade_dry_run",
]
