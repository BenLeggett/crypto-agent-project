"""Run Freqtrade in dry-run/paper mode through the project config."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from apps.research.freqtrade_commands import (
    FreqtradeCommandError,
    FreqtradeDryRunCommandRequest,
    run_freqtrade_dry_run,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="freqtrade/user_data/config.dryrun.json", help="Dry-run config path.")
    parser.add_argument("--userdir", default="freqtrade/user_data", help="Freqtrade user_data directory.")
    parser.add_argument("--strategy", default="RegimeBreakoutStrategy", help="Freqtrade strategy class.")
    parser.add_argument("--freqtrade-command", default="freqtrade", help="Freqtrade executable path or command name.")
    args = parser.parse_args(argv)

    try:
        result = run_freqtrade_dry_run(
            FreqtradeDryRunCommandRequest(
                config_path=Path(args.config),
                user_data_dir=Path(args.userdir),
                strategy=args.strategy,
                command=args.freqtrade_command,
            )
        )
    except (FreqtradeCommandError, ValueError) as exc:
        print(f"run_freqtrade_dryrun failed: {exc}", file=sys.stderr)
        return 1

    print(f"run_freqtrade_dryrun completed: {' '.join(result.command)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
