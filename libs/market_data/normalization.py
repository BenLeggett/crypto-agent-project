"""Normalization helpers for project-owned OHLCV datasets."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from libs.market_data.storage import OHLCVDatasetRow


class MarketDataNormalizationError(ValueError):
    """Raised when raw market-data records cannot be normalized."""


REQUIRED_OHLCV_FIELDS = (
    "symbol",
    "timeframe",
    "timestamp_ms",
    "open",
    "high",
    "low",
    "close",
    "volume",
)


def normalize_ohlcv_record(record: Mapping[str, Any], *, default_source: str = "project") -> OHLCVDatasetRow:
    missing = [field for field in REQUIRED_OHLCV_FIELDS if field not in record]
    if missing:
        raise MarketDataNormalizationError(f"Missing OHLCV field(s): {', '.join(missing)}")

    symbol = str(record["symbol"]).strip()
    timeframe = str(record["timeframe"]).strip()
    source = str(record.get("source") or default_source).strip()
    if not symbol:
        raise MarketDataNormalizationError("symbol is required")
    if not timeframe:
        raise MarketDataNormalizationError("timeframe is required")
    if not source:
        raise MarketDataNormalizationError("source is required")

    try:
        timestamp_ms = int(record["timestamp_ms"])
    except (TypeError, ValueError) as exc:
        raise MarketDataNormalizationError(f"Invalid timestamp_ms: {record['timestamp_ms']!r}") from exc
    if timestamp_ms < 0:
        raise MarketDataNormalizationError("timestamp_ms cannot be negative")

    return OHLCVDatasetRow(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_ms=timestamp_ms,
        open=_decimal(record["open"], "open"),
        high=_decimal(record["high"], "high"),
        low=_decimal(record["low"], "low"),
        close=_decimal(record["close"], "close"),
        volume=_decimal(record["volume"], "volume"),
        source=source,
    )


def normalize_ohlcv_records(
    records: Sequence[Mapping[str, Any]],
    *,
    default_source: str = "project",
) -> tuple[OHLCVDatasetRow, ...]:
    return tuple(normalize_ohlcv_record(record, default_source=default_source) for record in records)


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MarketDataNormalizationError(f"Invalid decimal field {field_name}: {value!r}") from exc
