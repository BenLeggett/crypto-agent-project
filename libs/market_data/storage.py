"""Storage layer for project-owned OHLCV datasets.

The real local backend uses Parquet for dataset files and DuckDB for analytics
registration. Imports for those packages are intentionally lazy so unit tests
and mock/local validation can run without installing data-engine dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol, Sequence

from libs.market_data.ccxt_client import OHLCV


class MarketDataStorageError(RuntimeError):
    """Raised when dataset persistence or analytics registration fails."""


@dataclass(frozen=True)
class OHLCVDatasetRow:
    symbol: str
    timeframe: str
    timestamp_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    source: str = "project"

    def to_record(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "timestamp_ms": self.timestamp_ms,
            "open": str(self.open),
            "high": str(self.high),
            "low": str(self.low),
            "close": str(self.close),
            "volume": str(self.volume),
            "source": self.source,
        }


@dataclass(frozen=True)
class StoredDataset:
    layer: str
    symbol: str
    timeframe: str
    path: Path
    row_count: int


@dataclass(frozen=True)
class MarketDataStoragePaths:
    parquet_root: Path = Path("data/parquet")
    duckdb_path: Path = Path("data/duckdb/market_data.duckdb")

    def ohlcv_path(self, *, layer: str, symbol: str, timeframe: str) -> Path:
        safe_symbol = _safe_path_part(symbol.replace("/", "_"))
        safe_timeframe = _safe_path_part(timeframe)
        return self.parquet_root / layer / "ohlcv" / safe_symbol / f"{safe_timeframe}.parquet"


class ParquetBackend(Protocol):
    def write_rows(self, path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
        ...

    def read_rows(self, path: Path) -> tuple[dict[str, Any], ...]:
        ...


class AnalyticsBackend(Protocol):
    def register_parquet(self, *, table_name: str, parquet_path: Path) -> None:
        ...

    def query_rows(
        self,
        *,
        table_name: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> tuple[dict[str, Any], ...]:
        ...


class PyArrowParquetBackend:
    """Parquet writer/reader backed by pyarrow when the optional extra is installed."""

    def write_rows(self, path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
        if not rows:
            raise MarketDataStorageError("Cannot write an empty dataset")
        try:
            import pyarrow as pa  # type: ignore[import-not-found]
            import pyarrow.parquet as pq  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MarketDataStorageError(
                "pyarrow is not installed; install the market-data extra or inject a test backend"
            ) from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.Table.from_pylist([dict(row) for row in rows])
        pq.write_table(table, path)

    def read_rows(self, path: Path) -> tuple[dict[str, Any], ...]:
        try:
            import pyarrow.parquet as pq  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MarketDataStorageError(
                "pyarrow is not installed; install the market-data extra or inject a test backend"
            ) from exc

        if not path.exists():
            raise MarketDataStorageError(f"Parquet dataset does not exist: {path}")
        table = pq.read_table(path)
        return tuple(dict(row) for row in table.to_pylist())


class DuckDBAnalyticsBackend:
    """DuckDB-backed analytics registration over Parquet datasets."""

    def __init__(self, database_path: Path = Path("data/duckdb/market_data.duckdb")) -> None:
        self._database_path = database_path

    def register_parquet(self, *, table_name: str, parquet_path: Path) -> None:
        _validate_table_name(table_name)
        try:
            import duckdb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MarketDataStorageError(
                "duckdb is not installed; install the market-data extra or inject a test backend"
            ) from exc

        if not parquet_path.exists():
            raise MarketDataStorageError(f"Parquet dataset does not exist: {parquet_path}")
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        with duckdb.connect(str(self._database_path)) as connection:
            connection.execute(
                f"CREATE OR REPLACE VIEW {table_name} AS SELECT * FROM read_parquet(?)",
                [str(parquet_path)],
            )

    def query_rows(
        self,
        *,
        table_name: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> tuple[dict[str, Any], ...]:
        _validate_table_name(table_name)
        try:
            import duckdb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise MarketDataStorageError(
                "duckdb is not installed; install the market-data extra or inject a test backend"
            ) from exc

        sql = f"SELECT * FROM {table_name}"
        conditions = []
        params: list[Any] = []
        if symbol is not None:
            conditions.append("symbol = ?")
            params.append(symbol)
        if timeframe is not None:
            conditions.append("timeframe = ?")
            params.append(timeframe)
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        sql += " ORDER BY timestamp_ms"
        if limit is not None:
            if limit <= 0:
                raise ValueError("limit must be positive when provided")
            sql += " LIMIT ?"
            params.append(limit)

        with duckdb.connect(str(self._database_path)) as connection:
            cursor = connection.execute(sql, params)
            columns = [column[0] for column in cursor.description]
            return tuple(dict(zip(columns, row)) for row in cursor.fetchall())


class MarketDataStorage:
    """Persist OHLCV rows to Parquet and register/query them through DuckDB."""

    def __init__(
        self,
        *,
        paths: MarketDataStoragePaths = MarketDataStoragePaths(),
        parquet_backend: Optional[ParquetBackend] = None,
        analytics_backend: Optional[AnalyticsBackend] = None,
    ) -> None:
        self._paths = paths
        self._parquet = parquet_backend or PyArrowParquetBackend()
        self._analytics = analytics_backend or DuckDBAnalyticsBackend(paths.duckdb_path)

    def write_ohlcv(
        self,
        rows: Sequence[OHLCVDatasetRow],
        *,
        layer: str = "raw",
    ) -> StoredDataset:
        if not rows:
            raise MarketDataStorageError("Cannot write an empty OHLCV dataset")
        _validate_layer(layer)
        symbol = rows[0].symbol
        timeframe = rows[0].timeframe
        for row in rows:
            if row.symbol != symbol or row.timeframe != timeframe:
                raise MarketDataStorageError("OHLCV dataset rows must share one symbol and timeframe")

        path = self._paths.ohlcv_path(layer=layer, symbol=symbol, timeframe=timeframe)
        self._parquet.write_rows(path, [row.to_record() for row in rows])
        return StoredDataset(layer=layer, symbol=symbol, timeframe=timeframe, path=path, row_count=len(rows))

    def register_dataset(self, dataset: StoredDataset, *, table_name: Optional[str] = None) -> str:
        selected_table = table_name or default_table_name(dataset)
        self._analytics.register_parquet(table_name=selected_table, parquet_path=dataset.path)
        return selected_table

    def query_ohlcv(
        self,
        *,
        table_name: str,
        symbol: Optional[str] = None,
        timeframe: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> tuple[dict[str, Any], ...]:
        return self._analytics.query_rows(
            table_name=table_name,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )


def rows_from_ohlcv(
    *,
    symbol: str,
    timeframe: str,
    rows: Sequence[OHLCV],
    source: str = "ccxt",
) -> tuple[OHLCVDatasetRow, ...]:
    if not symbol:
        raise ValueError("symbol is required")
    if not timeframe:
        raise ValueError("timeframe is required")
    if not source:
        raise ValueError("source is required")
    return tuple(
        OHLCVDatasetRow(
            symbol=symbol,
            timeframe=timeframe,
            timestamp_ms=row.timestamp_ms,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            volume=row.volume,
            source=source,
        )
        for row in rows
    )


def default_table_name(dataset: StoredDataset) -> str:
    return "_".join(
        [
            "ohlcv",
            _safe_path_part(dataset.layer),
            _safe_path_part(dataset.symbol.replace("/", "_")).lower(),
            _safe_path_part(dataset.timeframe).lower(),
        ]
    )


def _validate_layer(layer: str) -> None:
    if layer not in {"raw", "curated"}:
        raise ValueError("layer must be 'raw' or 'curated'")


def _safe_path_part(value: str) -> str:
    if not value:
        raise ValueError("path component cannot be empty")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return safe.strip("_")


def _validate_table_name(table_name: str) -> None:
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", table_name):
        raise ValueError(f"Invalid table name: {table_name!r}")
