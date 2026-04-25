from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from libs.market_data import (
    CCXTReadClient,
    MarketDataStorage,
    MarketDataStoragePaths,
    normalize_ohlcv_records,
    rows_from_ohlcv,
    validate_ohlcv_quality,
)


class FakeExchange:
    timeout = 0

    def fetch_ohlcv(self, symbol, timeframe="1h", since=None, limit=None):
        assert symbol == "BTC/USDT"
        assert timeframe == "1h"
        return [
            [1700000000000, "1.0", "2.0", "0.5", "1.5", "42.0"],
            [1700003600000, "1.5", "2.5", "1.0", "2.0", "43.0"],
            [1700007200000, "2.0", "3.0", "1.5", "2.5", "44.0"],
        ]

    def load_markets(self):
        return {}


class FakeParquetBackend:
    def __init__(self) -> None:
        self.writes: dict[Path, tuple[dict[str, Any], ...]] = {}

    def write_rows(self, path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
        self.writes[path] = tuple(dict(row) for row in rows)

    def read_rows(self, path: Path) -> tuple[dict[str, Any], ...]:
        return self.writes[path]


class FakeAnalyticsBackend:
    def __init__(self, parquet_backend: FakeParquetBackend) -> None:
        self._parquet = parquet_backend
        self.tables: dict[str, Path] = {}

    def register_parquet(self, *, table_name: str, parquet_path: Path) -> None:
        self.tables[table_name] = parquet_path

    def query_rows(
        self,
        *,
        table_name: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> tuple[dict[str, Any], ...]:
        rows = list(self._parquet.read_rows(self.tables[table_name]))
        if symbol is not None:
            rows = [row for row in rows if row["symbol"] == symbol]
        if timeframe is not None:
            rows = [row for row in rows if row["timeframe"] == timeframe]
        rows.sort(key=lambda row: row["timestamp_ms"])
        if limit is not None:
            rows = rows[:limit]
        return tuple(rows)


def test_ccxt_rows_can_be_validated_stored_registered_and_queried(tmp_path: Path) -> None:
    client = CCXTReadClient(FakeExchange())
    ohlcv = client.fetch_ohlcv("BTC/USDT", timeframe="1h")
    rows = rows_from_ohlcv(symbol="BTC/USDT", timeframe="1h", source="ccxt_fixture", rows=ohlcv)

    pre_storage_report = validate_ohlcv_quality(rows)

    parquet = FakeParquetBackend()
    analytics = FakeAnalyticsBackend(parquet)
    storage = MarketDataStorage(
        paths=MarketDataStoragePaths(parquet_root=tmp_path / "parquet", duckdb_path=tmp_path / "duckdb" / "db.duckdb"),
        parquet_backend=parquet,
        analytics_backend=analytics,
    )
    dataset = storage.write_ohlcv(rows, layer="raw")
    table_name = storage.register_dataset(dataset)
    queried_rows = normalize_ohlcv_records(
        storage.query_ohlcv(table_name=table_name, symbol="BTC/USDT", timeframe="1h")
    )
    post_storage_report = validate_ohlcv_quality(queried_rows)

    assert pre_storage_report.passed is True
    assert dataset.row_count == 3
    assert dataset.path == tmp_path / "parquet" / "raw" / "ohlcv" / "BTC_USDT" / "1h.parquet"
    assert table_name == "ohlcv_raw_btc_usdt_1h"
    assert queried_rows[0].open == Decimal("1.0")
    assert queried_rows[-1].close == Decimal("2.5")
    assert post_storage_report.passed is True
