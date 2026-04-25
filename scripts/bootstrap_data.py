"""Bootstrap historical OHLCV data through the selected Freqtrade foundation."""

from __future__ import annotations

import argparse
import sys
from typing import Optional, Sequence

from apps.collector.jobs import bootstrap_ohlcv
from libs.market_data.collectors import MarketDataCollectorError


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--symbols", nargs="*", help="Symbols such as BTC/USDT ETH/USDT. Defaults to config.")
    parser.add_argument("--timeframes", nargs="*", help="Timeframes such as 1h 4h. Defaults to config.")
    parser.add_argument("--exchange", help="Optional Freqtrade exchange name for public data download.")
    parser.add_argument("--timerange", help="Optional Freqtrade timerange, for example 20240101-20240201.")
    parser.add_argument("--freqtrade-command", default="freqtrade", help="Freqtrade executable path or command name.")
    args = parser.parse_args(argv)

    try:
        result = bootstrap_ohlcv(
            symbols=_normalize_args(args.symbols),
            timeframes=_normalize_args(args.timeframes),
            exchange=args.exchange,
            timerange=args.timerange,
            freqtrade_command=args.freqtrade_command,
        )
    except (MarketDataCollectorError, ValueError) as exc:
        print(f"bootstrap_data failed: {exc}", file=sys.stderr)
        return 1

    print(f"bootstrap_data completed via {result.provider}: {' '.join(result.command)}")
    return 0


def _normalize_args(values: Optional[Sequence[str]]) -> Optional[tuple[str, ...]]:
    if not values:
        return None
    normalized: list[str] = []
    for value in values:
        normalized.extend(part.strip() for part in value.split(",") if part.strip())
    return tuple(normalized) or None


if __name__ == "__main__":
    raise SystemExit(main())
