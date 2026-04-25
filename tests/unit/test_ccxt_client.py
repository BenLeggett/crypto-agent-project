from __future__ import annotations

import builtins
from decimal import Decimal

import pytest

from libs.market_data import CCXTReadClient, MarketDataClientError, create_public_ccxt_exchange


class FakeExchange:
    def __init__(self) -> None:
        self.timeout = 0
        self.fetch_calls = 0
        self.market_calls = 0
        self.failures_before_success = 0

    def fetch_ohlcv(self, symbol, timeframe="1h", since=None, limit=None):
        self.fetch_calls += 1
        if self.failures_before_success:
            self.failures_before_success -= 1
            raise RuntimeError("temporary outage")
        assert symbol == "BTC/USDT"
        assert timeframe == "1h"
        assert since == 123
        assert limit == 2
        return [
            [1700000000000, "1.0", "2.0", "0.5", "1.5", "42.0"],
            [1700003600000, 1.5, 2.5, 1.0, 2.0, 43.0],
        ]

    def load_markets(self):
        self.market_calls += 1
        return {
            "BTC/USDT": {"base": "BTC", "quote": "USDT", "active": True, "spot": True},
            "ETH/USDT": {"base": "ETH", "quote": "USDT", "active": False, "spot": True},
        }


def test_fetch_ohlcv_parses_rows_and_sets_timeout() -> None:
    exchange = FakeExchange()
    client = CCXTReadClient(exchange, timeout_ms=2500)

    rows = client.fetch_ohlcv("BTC/USDT", timeframe="1h", since=123, limit=2)

    assert exchange.timeout == 2500
    assert len(rows) == 2
    assert rows[0].timestamp_ms == 1700000000000
    assert rows[0].open == Decimal("1.0")
    assert rows[1].volume == Decimal("43.0")


def test_fetch_ohlcv_retries_transient_failures() -> None:
    exchange = FakeExchange()
    exchange.failures_before_success = 2
    sleeps: list[float] = []
    client = CCXTReadClient(
        exchange,
        max_retries=2,
        retry_sleep_seconds=0.1,
        sleeper=sleeps.append,
    )

    rows = client.fetch_ohlcv("BTC/USDT", timeframe="1h", since=123, limit=2)

    assert len(rows) == 2
    assert exchange.fetch_calls == 3
    assert sleeps == [0.1, 0.1]


def test_fetch_ohlcv_fails_after_retry_budget() -> None:
    exchange = FakeExchange()
    exchange.failures_before_success = 3
    client = CCXTReadClient(exchange, max_retries=1)

    with pytest.raises(MarketDataClientError, match="failed after 2 attempt"):
        client.fetch_ohlcv("BTC/USDT", timeframe="1h", since=123, limit=2)


def test_fetch_ohlcv_rejects_malformed_rows() -> None:
    class BadExchange(FakeExchange):
        def fetch_ohlcv(self, symbol, timeframe="1h", since=None, limit=None):
            return [[1700000000000, "1.0"]]

    client = CCXTReadClient(BadExchange())

    with pytest.raises(MarketDataClientError, match="Malformed OHLCV row"):
        client.fetch_ohlcv("BTC/USDT")


def test_load_market_metadata_parses_markets() -> None:
    client = CCXTReadClient(FakeExchange())

    markets = client.load_market_metadata()

    assert [market.symbol for market in markets] == ["BTC/USDT", "ETH/USDT"]
    assert markets[0].base == "BTC"
    assert markets[0].active is True
    assert markets[1].active is False


def test_client_rejects_invalid_constructor_values() -> None:
    with pytest.raises(ValueError, match="timeout_ms"):
        CCXTReadClient(FakeExchange(), timeout_ms=0)
    with pytest.raises(ValueError, match="max_retries"):
        CCXTReadClient(FakeExchange(), max_retries=-1)


def test_public_factory_requires_exchange_name() -> None:
    with pytest.raises((MarketDataClientError, ValueError)):
        create_public_ccxt_exchange("")


def test_public_factory_is_optional_without_ccxt_installed(monkeypatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "ccxt":
            raise ImportError("ccxt missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(MarketDataClientError, match="ccxt is not installed"):
        create_public_ccxt_exchange("binance")
