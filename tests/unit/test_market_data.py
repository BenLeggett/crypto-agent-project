from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from libs.market_data import (
    OHLCV,
    OHLCVCollectionRequest,
    build_freqtrade_download_command,
    normalize_ohlcv_records,
    rows_from_ohlcv,
    validate_ohlcv_quality,
)


def test_market_data_public_api_covers_collector_normalization_storage_and_quality() -> None:
    command = build_freqtrade_download_command(
        OHLCVCollectionRequest(
            symbols=("BTC/USDT",),
            timeframes=("1h",),
            exchange="binance",
            days=2,
        )
    )

    rows = rows_from_ohlcv(
        symbol="BTC/USDT",
        timeframe="1h",
        source="fixture",
        rows=(
            OHLCV(
                timestamp_ms=1700000000000,
                open=Decimal("1.0"),
                high=Decimal("2.0"),
                low=Decimal("0.5"),
                close=Decimal("1.5"),
                volume=Decimal("42.0"),
            ),
            OHLCV(
                timestamp_ms=1700003600000,
                open=Decimal("1.5"),
                high=Decimal("2.5"),
                low=Decimal("1.0"),
                close=Decimal("2.0"),
                volume=Decimal("43.0"),
            ),
        ),
    )
    normalized = normalize_ohlcv_records([row.to_record() for row in rows])
    report = validate_ohlcv_quality(normalized)

    assert command[:2] == ("freqtrade", "download-data")
    assert str(Path("configs/dry_run/freqtrade.json")) in command
    assert "--exchange" in command
    assert "--days" in command
    assert normalized == rows
    assert report.passed is True
