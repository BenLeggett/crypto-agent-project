"""OHLCV collection orchestration.

The selected foundation is Freqtrade. This module builds explicit
``freqtrade download-data`` commands and runs them through an injected command
runner so tests can validate behavior without installing Freqtrade, reaching an
exchange, or requiring credentials.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Protocol, Sequence


class MarketDataCollectorError(RuntimeError):
    """Raised when a market-data collection job cannot be prepared or run."""


@dataclass(frozen=True)
class CommandResult:
    command: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner(Protocol):
    """Side-effect boundary for running external framework commands."""

    def run(self, command: Sequence[str], *, cwd: Optional[Path] = None) -> CommandResult:
        ...


class SubprocessCommandRunner:
    """Run commands without a shell so arguments stay explicit and testable."""

    def run(self, command: Sequence[str], *, cwd: Optional[Path] = None) -> CommandResult:
        try:
            completed = subprocess.run(
                list(command),
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError as exc:
            raise MarketDataCollectorError(
                f"Command not found: {command[0]!r}. Install the selected trading foundation or use a mock runner."
            ) from exc

        return CommandResult(
            command=tuple(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


@dataclass(frozen=True)
class OHLCVCollectionRequest:
    symbols: tuple[str, ...]
    timeframes: tuple[str, ...]
    config_path: Path = Path("configs/dry_run/freqtrade.json")
    user_data_dir: Path = Path("freqtrade/user_data")
    data_dir: Optional[Path] = None
    exchange: Optional[str] = None
    timerange: Optional[str] = None
    days: Optional[int] = None
    prepend: bool = False
    erase: bool = False
    command: str = "freqtrade"

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError("command is required")
        if not self.symbols:
            raise ValueError("at least one symbol is required")
        if not self.timeframes:
            raise ValueError("at least one timeframe is required")
        if self.days is not None and self.days <= 0:
            raise ValueError("days must be positive when provided")


@dataclass(frozen=True)
class OHLCVCollectionResult:
    provider: str
    operation: str
    command: tuple[str, ...]
    stdout: str
    stderr: str


def build_freqtrade_download_command(request: OHLCVCollectionRequest) -> tuple[str, ...]:
    """Build the Freqtrade OHLCV download command for bootstrap/update jobs."""
    command = [
        request.command,
        "download-data",
        "--config",
        str(request.config_path),
        "--userdir",
        str(request.user_data_dir),
        "--trading-mode",
        "spot",
        "--pairs",
        *request.symbols,
        "--timeframes",
        *request.timeframes,
    ]
    if request.data_dir is not None:
        command.extend(["--datadir", str(request.data_dir)])
    if request.exchange:
        command.extend(["--exchange", request.exchange])
    if request.timerange:
        command.extend(["--timerange", request.timerange])
    if request.days is not None:
        command.extend(["--days", str(request.days)])
    if request.prepend:
        command.append("--prepend")
    if request.erase:
        command.append("--erase")
    return tuple(command)


def run_freqtrade_ohlcv_download(
    request: OHLCVCollectionRequest,
    *,
    operation: str,
    runner: Optional[CommandRunner] = None,
    cwd: Optional[Path] = None,
) -> OHLCVCollectionResult:
    """Run a Freqtrade-backed OHLCV collection command."""
    if operation not in {"bootstrap", "update"}:
        raise ValueError(f"Unsupported collection operation: {operation!r}")

    command = build_freqtrade_download_command(request)
    command_runner = runner or SubprocessCommandRunner()
    result = command_runner.run(command, cwd=cwd)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "no command output"
        raise MarketDataCollectorError(
            f"Freqtrade OHLCV {operation} failed with exit code {result.returncode}: {detail}"
        )

    return OHLCVCollectionResult(
        provider="freqtrade",
        operation=operation,
        command=result.command,
        stdout=result.stdout,
        stderr=result.stderr,
    )
