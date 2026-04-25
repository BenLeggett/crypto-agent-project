"""Market-data collector jobs.

These jobs prefer the selected Freqtrade foundation for OHLCV downloads. They
remain testable through an injected command runner and do not require exchange
credentials for local/mock validation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from libs.config import ProjectConfig, load_config
from libs.market_data.collectors import (
    CommandRunner,
    OHLCVCollectionRequest,
    OHLCVCollectionResult,
    run_freqtrade_ohlcv_download,
)

DEFAULT_CONFIG_PATH = Path("configs/dry_run/freqtrade.json")
DEFAULT_USER_DATA_DIR = Path("freqtrade/user_data")
DEFAULT_UPDATE_DAYS = 7


def bootstrap_ohlcv(
    *,
    config: Optional[ProjectConfig] = None,
    symbols: Optional[Sequence[str]] = None,
    timeframes: Optional[Sequence[str]] = None,
    exchange: Optional[str] = None,
    timerange: Optional[str] = None,
    freqtrade_command: str = "freqtrade",
    runner: Optional[CommandRunner] = None,
) -> OHLCVCollectionResult:
    project_config = config or load_config()
    request = _build_request(
        project_config,
        symbols=symbols,
        timeframes=timeframes,
        exchange=exchange,
        timerange=timerange,
        freqtrade_command=freqtrade_command,
    )
    return run_freqtrade_ohlcv_download(request, operation="bootstrap", runner=runner)


def update_ohlcv(
    *,
    config: Optional[ProjectConfig] = None,
    symbols: Optional[Sequence[str]] = None,
    timeframes: Optional[Sequence[str]] = None,
    exchange: Optional[str] = None,
    days: int = DEFAULT_UPDATE_DAYS,
    freqtrade_command: str = "freqtrade",
    runner: Optional[CommandRunner] = None,
) -> OHLCVCollectionResult:
    project_config = config or load_config()
    request = _build_request(
        project_config,
        symbols=symbols,
        timeframes=timeframes,
        exchange=exchange,
        days=days,
        freqtrade_command=freqtrade_command,
    )
    return run_freqtrade_ohlcv_download(request, operation="update", runner=runner)


def _build_request(
    config: ProjectConfig,
    *,
    symbols: Optional[Sequence[str]],
    timeframes: Optional[Sequence[str]],
    exchange: Optional[str],
    timerange: Optional[str] = None,
    days: Optional[int] = None,
    freqtrade_command: str,
) -> OHLCVCollectionRequest:
    selected_symbols = tuple(symbols or config.symbols.symbols)
    selected_timeframes = tuple(timeframes or config.symbols.timeframes)
    if config.app.trading_foundation != "freqtrade":
        raise ValueError(f"Unsupported trading foundation: {config.app.trading_foundation!r}")

    return OHLCVCollectionRequest(
        symbols=selected_symbols,
        timeframes=selected_timeframes,
        config_path=DEFAULT_CONFIG_PATH,
        user_data_dir=DEFAULT_USER_DATA_DIR,
        exchange=exchange,
        timerange=timerange,
        days=days,
        command=freqtrade_command,
    )
