"""Run a Freqtrade backtest through the dry-run project config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from apps.research.freqtrade_commands import (
    FreqtradeBacktestCommandRequest,
    FreqtradeCommandError,
    run_freqtrade_backtest,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timerange", help="Optional Freqtrade timerange, for example 20240101-20240201.")
    parser.add_argument("--timeframe", help="Optional timeframe override, for example 4h.")
    parser.add_argument("--export-filename", help="Optional Freqtrade backtest export path.")
    parser.add_argument("--config", default="freqtrade/user_data/config.dryrun.json", help="Dry-run config path.")
    parser.add_argument("--userdir", default="freqtrade/user_data", help="Freqtrade user_data directory.")
    parser.add_argument("--strategy", default="RegimeBreakoutStrategy", help="Freqtrade strategy class.")
    parser.add_argument("--freqtrade-command", default="freqtrade", help="Freqtrade executable path or command name.")
    args = parser.parse_args(argv)

    try:
        result = run_freqtrade_backtest(
            FreqtradeBacktestCommandRequest(
                config_path=Path(args.config),
                user_data_dir=Path(args.userdir),
                strategy=args.strategy,
                command=args.freqtrade_command,
                timerange=args.timerange,
                timeframe=args.timeframe,
                export_filename=Path(args.export_filename) if args.export_filename else None,
            )
        )
    except (FreqtradeCommandError, ValueError) as exc:
        print(f"run_freqtrade_backtest failed: {exc}", file=sys.stderr)
        return 1

    print(f"run_freqtrade_backtest completed: {' '.join(result.command)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
