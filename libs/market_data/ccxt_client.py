"""Narrow read-only CCXT wrapper for project-specific market data needs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence


class MarketDataClientError(RuntimeError):
    """Raised when market-data reads fail or return malformed data."""


class CCXTExchange(Protocol):
    """Small subset of CCXT exchange behavior used by this project."""

    timeout: int

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> Sequence[Sequence[Any]]:
        ...

    def load_markets(self) -> Mapping[str, Mapping[str, Any]]:
        ...


@dataclass(frozen=True)
class OHLCV:
    timestamp_ms: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True)
class MarketMetadata:
    symbol: str
    base: str
    quote: str
    active: bool
    spot: bool
    raw: Mapping[str, Any]


class CCXTReadClient:
    """Read-only wrapper with explicit retries for OHLCV and market metadata."""

    def __init__(
        self,
        exchange: CCXTExchange,
        *,
        timeout_ms: int = 10_000,
        max_retries: int = 2,
        retry_sleep_seconds: float = 0.0,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_sleep_seconds < 0:
            raise ValueError("retry_sleep_seconds cannot be negative")

        self._exchange = exchange
        self._max_retries = max_retries
        self._retry_sleep_seconds = retry_sleep_seconds
        self._sleeper = sleeper
        self._exchange.timeout = timeout_ms

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: Optional[int] = None,
    ) -> tuple[OHLCV, ...]:
        if not symbol:
            raise ValueError("symbol is required")
        if not timeframe:
            raise ValueError("timeframe is required")

        rows = self._with_retries(
            lambda: self._exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit),
            operation=f"fetch_ohlcv:{symbol}:{timeframe}",
        )
        return tuple(_parse_ohlcv(row) for row in rows)

    def load_market_metadata(self) -> tuple[MarketMetadata, ...]:
        markets = self._with_retries(self._exchange.load_markets, operation="load_markets")
        if not isinstance(markets, Mapping):
            raise MarketDataClientError("load_markets returned a non-mapping response")
        return tuple(_parse_market(symbol, market) for symbol, market in markets.items())

    def _with_retries(self, operation_fn: Callable[[], Any], *, operation: str) -> Any:
        attempts = self._max_retries + 1
        last_error: Optional[BaseException] = None
        for attempt in range(1, attempts + 1):
            try:
                return operation_fn()
            except Exception as exc:  # CCXT raises provider-specific subclasses.
                last_error = exc
                if attempt == attempts:
                    break
                if self._retry_sleep_seconds:
                    self._sleeper(self._retry_sleep_seconds)
        raise MarketDataClientError(f"{operation} failed after {attempts} attempt(s)") from last_error


def create_public_ccxt_exchange(exchange_name: str, *, timeout_ms: int = 10_000) -> CCXTExchange:
    """Create a public CCXT exchange instance without credentials.

    This is intentionally optional so tests and local development can use mocks
    without requiring network packages or secrets.
    """
    if not exchange_name:
        raise ValueError("exchange_name is required")
    try:
        import ccxt  # type: ignore[import-not-found]
    except ImportError as exc:
        raise MarketDataClientError("ccxt is not installed; use an injected mock or install ccxt") from exc

    exchange_cls = getattr(ccxt, exchange_name, None)
    if exchange_cls is None:
        raise MarketDataClientError(f"Unsupported CCXT exchange: {exchange_name}")
    exchange = exchange_cls({"enableRateLimit": True, "timeout": timeout_ms})
    exchange.timeout = timeout_ms
    return exchange


def _parse_ohlcv(row: Sequence[Any]) -> OHLCV:
    if len(row) < 6:
        raise MarketDataClientError(f"Malformed OHLCV row: {row!r}")
    try:
        return OHLCV(
            timestamp_ms=int(row[0]),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
        )
    except Exception as exc:
        raise MarketDataClientError(f"Malformed OHLCV row: {row!r}") from exc


def _parse_market(symbol: str, market: Mapping[str, Any]) -> MarketMetadata:
    if not symbol:
        raise MarketDataClientError("Market metadata contained an empty symbol")
    return MarketMetadata(
        symbol=symbol,
        base=str(market.get("base") or ""),
        quote=str(market.get("quote") or ""),
        active=bool(market.get("active", False)),
        spot=bool(market.get("spot", False)),
        raw=market,
    )
