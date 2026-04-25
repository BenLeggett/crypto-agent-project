from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

import builtins
import pytest

from libs.market_data import (
    DuckDBAnalyticsBackend,
    MarketDataStorage,
    MarketDataStorageError,
    MarketDataStoragePaths,
    OHLCV,
    OHLCVDatasetRow,
    PyArrowParquetBackend,
    default_table_name,
    rows_from_ohlcv,
)


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


def test_rows_from_ohlcv_preserves_decimal_values() -> None:
    rows = rows_from_ohlcv(
        symbol="BTC/USDT",
        timeframe="1h",
        source="fixture",
        rows=(
            OHLCV(
                timestamp_ms=1700000000000,
                open=Decimal("1.1"),
                high=Decimal("2.2"),
                low=Decimal("0.9"),
                close=Decimal("1.8"),
                volume=Decimal("42.0"),
            ),
        ),
    )

    assert rows[0].symbol == "BTC/USDT"
    assert rows[0].open == Decimal("1.1")
    assert rows[0].source == "fixture"
    assert rows[0].to_record()["open"] == "1.1"


def test_storage_writes_parquet_path_and_registers_duckdb_table(tmp_path: Path) -> None:
    parquet = FakeParquetBackend()
    analytics = FakeAnalyticsBackend(parquet)
    storage = MarketDataStorage(
        paths=MarketDataStoragePaths(parquet_root=tmp_path / "parquet", duckdb_path=tmp_path / "duckdb" / "db.duckdb"),
        parquet_backend=parquet,
        analytics_backend=analytics,
    )
    rows = _sample_rows()

    dataset = storage.write_ohlcv(rows, layer="raw")
    table_name = storage.register_dataset(dataset)

    assert dataset.path == tmp_path / "parquet" / "raw" / "ohlcv" / "BTC_USDT" / "1h.parquet"
    assert dataset.row_count == 2
    assert table_name == "ohlcv_raw_btc_usdt_1h"
    assert analytics.tables[table_name] == dataset.path
    assert parquet.writes[dataset.path][0]["close"] == "1.5"


def test_storage_queries_registered_rows_in_timestamp_order(tmp_path: Path) -> None:
    parquet = FakeParquetBackend()
    analytics = FakeAnalyticsBackend(parquet)
    storage = MarketDataStorage(
        paths=MarketDataStoragePaths(parquet_root=tmp_path / "parquet"),
        parquet_backend=parquet,
        analytics_backend=analytics,
    )
    dataset = storage.write_ohlcv(tuple(reversed(_sample_rows())), layer="curated")
    table_name = storage.register_dataset(dataset)

    rows = storage.query_ohlcv(table_name=table_name, symbol="BTC/USDT", timeframe="1h", limit=1)

    assert len(rows) == 1
    assert rows[0]["timestamp_ms"] == 1700000000000


def test_storage_rejects_empty_or_mixed_datasets(tmp_path: Path) -> None:
    storage = MarketDataStorage(
        paths=MarketDataStoragePaths(parquet_root=tmp_path / "parquet"),
        parquet_backend=FakeParquetBackend(),
        analytics_backend=FakeAnalyticsBackend(FakeParquetBackend()),
    )

    with pytest.raises(MarketDataStorageError, match="empty"):
        storage.write_ohlcv(())

    mixed = _sample_rows() + (
        OHLCVDatasetRow(
            symbol="ETH/USDT",
            timeframe="1h",
            timestamp_ms=1700007200000,
            open=Decimal("1"),
            high=Decimal("1"),
            low=Decimal("1"),
            close=Decimal("1"),
            volume=Decimal("1"),
        ),
    )
    with pytest.raises(MarketDataStorageError, match="one symbol and timeframe"):
        storage.write_ohlcv(mixed)


def test_default_table_name_is_duckdb_safe() -> None:
    dataset = type(
        "Dataset",
        (),
        {"layer": "raw", "symbol": "BTC/USDT", "timeframe": "4h"},
    )()

    assert default_table_name(dataset) == "ohlcv_raw_btc_usdt_4h"


def test_pyarrow_backend_reports_missing_optional_dependency(monkeypatch, tmp_path: Path) -> None:
    _block_import(monkeypatch, "pyarrow")

    with pytest.raises(MarketDataStorageError, match="pyarrow is not installed"):
        PyArrowParquetBackend().write_rows(tmp_path / "rows.parquet", [{"symbol": "BTC/USDT"}])


def test_duckdb_backend_reports_missing_optional_dependency(monkeypatch, tmp_path: Path) -> None:
    _block_import(monkeypatch, "duckdb")

    with pytest.raises(MarketDataStorageError, match="duckdb is not installed"):
        DuckDBAnalyticsBackend(tmp_path / "db.duckdb").register_parquet(
            table_name="ohlcv_raw_btc_usdt_1h",
            parquet_path=tmp_path / "rows.parquet",
        )


def _sample_rows() -> tuple[OHLCVDatasetRow, ...]:
    return (
        OHLCVDatasetRow(
            symbol="BTC/USDT",
            timeframe="1h",
            timestamp_ms=1700000000000,
            open=Decimal("1.0"),
            high=Decimal("2.0"),
            low=Decimal("0.5"),
            close=Decimal("1.5"),
            volume=Decimal("42.0"),
            source="fixture",
        ),
        OHLCVDatasetRow(
            symbol="BTC/USDT",
            timeframe="1h",
            timestamp_ms=1700003600000,
            open=Decimal("1.5"),
            high=Decimal("2.5"),
            low=Decimal("1.0"),
            close=Decimal("2.0"),
            volume=Decimal("43.0"),
            source="fixture",
        ),
    )


def _block_import(monkeypatch, blocked_name: str) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == blocked_name or name.startswith(f"{blocked_name}."):
            raise ImportError(f"{blocked_name} missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
