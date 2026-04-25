"""Deterministic market-data quality checks."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from libs.market_data.storage import OHLCVDatasetRow


class MarketDataQualityError(ValueError):
    """Raised when a dataset fails quality checks."""


@dataclass(frozen=True)
class QualityIssue:
    code: str
    message: str
    timestamp_ms: Optional[int] = None


@dataclass(frozen=True)
class QualityReport:
    row_count: int
    issues: tuple[QualityIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


def validate_ohlcv_quality(
    rows: Sequence[OHLCVDatasetRow],
    *,
    expected_interval_ms: Optional[int] = None,
) -> QualityReport:
    issues: list[QualityIssue] = []
    if not rows:
        return QualityReport(row_count=0, issues=(QualityIssue("empty_dataset", "OHLCV dataset is empty"),))

    symbol = rows[0].symbol
    timeframe = rows[0].timeframe
    interval_ms = expected_interval_ms if expected_interval_ms is not None else timeframe_to_milliseconds(timeframe)
    if interval_ms <= 0:
        issues.append(QualityIssue("invalid_interval", "Expected candle interval must be positive"))

    seen_timestamps: set[int] = set()
    previous_timestamp: Optional[int] = None
    for row in rows:
        if row.symbol != symbol or row.timeframe != timeframe:
            issues.append(
                QualityIssue(
                    "mixed_dataset",
                    "Dataset contains more than one symbol or timeframe",
                    row.timestamp_ms,
                )
            )
        issues.extend(_validate_candle_shape(row))

        if row.timestamp_ms in seen_timestamps:
            issues.append(QualityIssue("duplicate_timestamp", "Duplicate candle timestamp", row.timestamp_ms))
        seen_timestamps.add(row.timestamp_ms)

        if previous_timestamp is not None:
            if row.timestamp_ms <= previous_timestamp:
                issues.append(QualityIssue("out_of_order", "Candle timestamp is not strictly increasing", row.timestamp_ms))
            elif interval_ms > 0 and row.timestamp_ms - previous_timestamp != interval_ms:
                issues.append(
                    QualityIssue(
                        "missing_candle_gap",
                        f"Expected interval {interval_ms} ms, got {row.timestamp_ms - previous_timestamp} ms",
                        row.timestamp_ms,
                    )
                )
        previous_timestamp = row.timestamp_ms

    return QualityReport(row_count=len(rows), issues=tuple(issues))


def assert_ohlcv_quality(
    rows: Sequence[OHLCVDatasetRow],
    *,
    expected_interval_ms: Optional[int] = None,
) -> QualityReport:
    report = validate_ohlcv_quality(rows, expected_interval_ms=expected_interval_ms)
    if not report.passed:
        first_issue = report.issues[0]
        raise MarketDataQualityError(f"{first_issue.code}: {first_issue.message}")
    return report


def timeframe_to_milliseconds(timeframe: str) -> int:
    match = re.fullmatch(r"(\d+)([mhd])", timeframe.strip().lower())
    if not match:
        raise MarketDataQualityError(f"Unsupported timeframe: {timeframe!r}")
    quantity = int(match.group(1))
    unit = match.group(2)
    multiplier = {"m": 60_000, "h": 3_600_000, "d": 86_400_000}[unit]
    return quantity * multiplier


def _validate_candle_shape(row: OHLCVDatasetRow) -> tuple[QualityIssue, ...]:
    issues: list[QualityIssue] = []
    finite_prices = all(_is_finite(value) for value in (row.open, row.high, row.low, row.close))
    finite_volume = _is_finite(row.volume)
    if not finite_prices:
        issues.append(QualityIssue("non_finite_price", "OHLC price fields must be finite decimals", row.timestamp_ms))
    if not finite_volume:
        issues.append(QualityIssue("non_finite_volume", "Volume must be a finite decimal", row.timestamp_ms))
    if not finite_prices or not finite_volume:
        return tuple(issues)

    if row.open < 0 or row.high < 0 or row.low < 0 or row.close < 0:
        issues.append(QualityIssue("negative_price", "OHLC price fields cannot be negative", row.timestamp_ms))
    if row.volume < 0:
        issues.append(QualityIssue("negative_volume", "Volume cannot be negative", row.timestamp_ms))
    if row.high < max(row.open, row.close, row.low):
        issues.append(QualityIssue("malformed_candle", "High is below one or more OHLC fields", row.timestamp_ms))
    if row.low > min(row.open, row.close, row.high):
        issues.append(QualityIssue("malformed_candle", "Low is above one or more OHLC fields", row.timestamp_ms))
    return tuple(issues)


def _is_finite(value: Decimal) -> bool:
    return value.is_finite()
