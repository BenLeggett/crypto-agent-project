"""Validate a stored OHLCV dataset before curated promotion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from libs.market_data.normalization import MarketDataNormalizationError, normalize_ohlcv_records
from libs.market_data.quality_checks import MarketDataQualityError, validate_ohlcv_quality
from libs.market_data.storage import MarketDataStorageError, PyArrowParquetBackend


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--path", required=True, help="Parquet dataset path to validate.")
    parser.add_argument("--expected-interval-ms", type=int, help="Optional explicit candle interval in milliseconds.")
    args = parser.parse_args(argv)

    try:
        raw_rows = PyArrowParquetBackend().read_rows(Path(args.path))
        rows = normalize_ohlcv_records(raw_rows)
        report = validate_ohlcv_quality(rows, expected_interval_ms=args.expected_interval_ms)
    except (MarketDataStorageError, MarketDataNormalizationError, MarketDataQualityError, ValueError) as exc:
        print(f"validate_data failed: {exc}", file=sys.stderr)
        return 1

    if not report.passed:
        for issue in report.issues:
            timestamp = "" if issue.timestamp_ms is None else f" timestamp_ms={issue.timestamp_ms}"
            print(f"{issue.code}:{timestamp} {issue.message}", file=sys.stderr)
        return 1

    print(f"validate_data passed: {report.row_count} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
