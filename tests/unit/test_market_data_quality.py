from __future__ import annotations

from decimal import Decimal

import pytest

import scripts.validate_data as validate_script
from libs.market_data import (
    MarketDataNormalizationError,
    MarketDataQualityError,
    OHLCVDatasetRow,
    assert_ohlcv_quality,
    normalize_ohlcv_record,
    normalize_ohlcv_records,
    timeframe_to_milliseconds,
    validate_ohlcv_quality,
)


def test_normalize_ohlcv_record_converts_strings_to_typed_row() -> None:
    row = normalize_ohlcv_record(
        {
            "symbol": " BTC/USDT ",
            "timeframe": "1h",
            "timestamp_ms": "1700000000000",
            "open": "1.0",
            "high": "2.0",
            "low": "0.5",
            "close": "1.5",
            "volume": "42.0",
        },
        default_source="fixture",
    )

    assert row.symbol == "BTC/USDT"
    assert row.open == Decimal("1.0")
    assert row.source == "fixture"


def test_normalize_ohlcv_record_rejects_missing_or_bad_fields() -> None:
    with pytest.raises(MarketDataNormalizationError, match="Missing OHLCV"):
        normalize_ohlcv_record({"symbol": "BTC/USDT"})
    with pytest.raises(MarketDataNormalizationError, match="Invalid decimal"):
        normalize_ohlcv_record(
            {
                "symbol": "BTC/USDT",
                "timeframe": "1h",
                "timestamp_ms": 1,
                "open": "not-a-number",
                "high": "2",
                "low": "1",
                "close": "1.5",
                "volume": "1",
            }
        )


def test_quality_report_passes_clean_dataset() -> None:
    report = validate_ohlcv_quality(_rows())

    assert report.passed is True
    assert report.row_count == 3
    assert report.issues == ()


def test_quality_report_detects_invalid_datasets() -> None:
    cases = [
        ((_row(0), _row(0)), "duplicate_timestamp"),
        ((_row(60), _row(0)), "out_of_order"),
        ((_row(0), _row(120)), "missing_candle_gap"),
        ((_row(0, high=Decimal("0.75")),), "malformed_candle"),
        ((_row(0, low=Decimal("1.25")),), "malformed_candle"),
        ((_row(0, volume=Decimal("-1")),), "negative_volume"),
        ((_row(0, close=Decimal("-1")),), "negative_price"),
    ]

    for rows, code in cases:
        report = validate_ohlcv_quality(rows, expected_interval_ms=60_000)

        assert code in {issue.code for issue in report.issues}
        assert report.passed is False


def test_quality_report_detects_mixed_symbol_or_timeframe() -> None:
    report = validate_ohlcv_quality((_row(0), _row(60, symbol="ETH/USDT")), expected_interval_ms=60_000)

    assert "mixed_dataset" in {issue.code for issue in report.issues}


def test_assert_quality_raises_first_issue() -> None:
    with pytest.raises(MarketDataQualityError, match="empty_dataset"):
        assert_ohlcv_quality(())


def test_timeframe_to_milliseconds_supports_expected_units() -> None:
    assert timeframe_to_milliseconds("15m") == 900_000
    assert timeframe_to_milliseconds("4h") == 14_400_000
    assert timeframe_to_milliseconds("1d") == 86_400_000


def test_validate_data_script_reports_success(monkeypatch, capsys) -> None:
    class FakeParquetBackend:
        def read_rows(self, path):
            return tuple(row.to_record() for row in _rows())

    monkeypatch.setattr(validate_script, "PyArrowParquetBackend", FakeParquetBackend)

    exit_code = validate_script.main(["--path", "unused.parquet"])

    assert exit_code == 0
    assert "passed: 3 row" in capsys.readouterr().out


def test_validate_data_script_reports_quality_failure(monkeypatch, capsys) -> None:
    class FakeParquetBackend:
        def read_rows(self, path):
            return tuple(row.to_record() for row in (_row(0), _row(120)))

    monkeypatch.setattr(validate_script, "PyArrowParquetBackend", FakeParquetBackend)

    exit_code = validate_script.main(["--path", "unused.parquet", "--expected-interval-ms", "60000"])

    assert exit_code == 1
    assert "missing_candle_gap" in capsys.readouterr().err


def _rows() -> tuple[OHLCVDatasetRow, ...]:
    return (_row(0), _row(1), _row(2))


def _row(
    minute_offset: int,
    *,
    symbol: str = "BTC/USDT",
    timeframe: str = "1m",
    high: Decimal = Decimal("2.0"),
    low: Decimal = Decimal("0.5"),
    close: Decimal = Decimal("1.5"),
    volume: Decimal = Decimal("42.0"),
) -> OHLCVDatasetRow:
    return OHLCVDatasetRow(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_ms=1700000000000 + minute_offset * 60_000,
        open=Decimal("1.0"),
        high=high,
        low=low,
        close=close,
        volume=volume,
        source="fixture",
    )
