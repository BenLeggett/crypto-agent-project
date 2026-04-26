from __future__ import annotations

from decimal import Decimal

import pytest

from libs.strategy.universe import (
    SymbolMarketInfo,
    UniverseRejectionReason,
    UniverseSelectionConfig,
    select_universe,
)


def test_select_universe_preserves_config_order() -> None:
    selection = select_universe(
        UniverseSelectionConfig(
            configured_symbols=("BTC/USDT", "ETH/USDT", "SOL/USDT"),
        )
    )

    assert selection.selected_symbols == ("BTC/USDT", "ETH/USDT", "SOL/USDT")
    assert selection.rejected_symbols == ()
    assert selection.is_empty is False


def test_select_universe_applies_denylist_duplicates_and_max_symbols() -> None:
    selection = select_universe(
        UniverseSelectionConfig(
            configured_symbols=(
                "BTC/USDT",
                "ETH/USDT",
                "btc/usdt",
                "SOL/USDT",
                "AVAX/USDT",
            ),
            denied_symbols=("ETH/USDT",),
            max_symbols=2,
        )
    )

    assert selection.selected_symbols == ("BTC/USDT", "SOL/USDT")
    assert [rejection.reason for rejection in selection.rejected_symbols] == [
        UniverseRejectionReason.DENYLISTED,
        UniverseRejectionReason.DUPLICATE_SYMBOL,
        UniverseRejectionReason.MAX_SYMBOLS_REACHED,
    ]


def test_select_universe_filters_by_metadata_without_fetching_it() -> None:
    market_info = {
        "BTC/USDT": SymbolMarketInfo(
            symbol="BTC/USDT",
            base_asset="BTC",
            quote_asset="USDT",
            is_active=True,
            min_notional=Decimal("10"),
        ),
        "ETH/USDT": SymbolMarketInfo(
            symbol="ETH/USDT",
            base_asset="ETH",
            quote_asset="USDT",
            is_active=False,
            min_notional=Decimal("10"),
        ),
        "SOL/BTC": SymbolMarketInfo(
            symbol="SOL/BTC",
            base_asset="SOL",
            quote_asset="BTC",
            is_active=True,
            min_notional=Decimal("10"),
        ),
        "ADA/USDT": SymbolMarketInfo(
            symbol="ADA/USDT",
            base_asset="ADA",
            quote_asset="USDT",
            is_active=True,
            min_notional=Decimal("1"),
        ),
    }

    selection = select_universe(
        UniverseSelectionConfig(
            configured_symbols=("BTC/USDT", "ETH/USDT", "SOL/BTC", "ADA/USDT"),
            allowed_quote_assets=("USDT",),
            min_notional_floor=Decimal("5"),
            require_active=True,
        ),
        market_info=market_info,
    )

    assert selection.selected_symbols == ("BTC/USDT",)
    assert [rejection.reason for rejection in selection.rejected_symbols] == [
        UniverseRejectionReason.INACTIVE_MARKET,
        UniverseRejectionReason.QUOTE_ASSET_NOT_ALLOWED,
        UniverseRejectionReason.BELOW_MIN_NOTIONAL,
    ]


def test_select_universe_can_require_metadata() -> None:
    selection = select_universe(
        UniverseSelectionConfig(
            configured_symbols=("BTC/USDT", "ETH/USDT"),
            require_metadata=True,
        ),
        market_info={
            "BTC/USDT": SymbolMarketInfo(
                symbol="BTC/USDT",
                base_asset="BTC",
                quote_asset="USDT",
            )
        },
    )

    assert selection.selected_symbols == ("BTC/USDT",)
    assert selection.rejected_symbols[0].symbol == "ETH/USDT"
    assert selection.rejected_symbols[0].reason is UniverseRejectionReason.MISSING_METADATA


def test_select_universe_returns_empty_selection_with_reasons() -> None:
    selection = select_universe(
        UniverseSelectionConfig(
            configured_symbols=("", " ETH/USDT "),
            denied_symbols=("ETH/USDT",),
        )
    )

    assert selection.selected_symbols == ()
    assert selection.is_empty is True
    assert [rejection.reason for rejection in selection.rejected_symbols] == [
        UniverseRejectionReason.EMPTY_SYMBOL,
        UniverseRejectionReason.DENYLISTED,
    ]


def test_universe_config_fails_fast_on_invalid_bounds() -> None:
    with pytest.raises(ValueError, match="max_symbols"):
        UniverseSelectionConfig(configured_symbols=("BTC/USDT",), max_symbols=0)

    with pytest.raises(ValueError, match="min_notional_floor"):
        UniverseSelectionConfig(
            configured_symbols=("BTC/USDT",),
            min_notional_floor=Decimal("-1"),
        )

    with pytest.raises(TypeError, match="Decimal"):
        UniverseSelectionConfig(
            configured_symbols=("BTC/USDT",),
            min_notional_floor="1",  # type: ignore[arg-type]
        )


def test_market_info_is_immutable() -> None:
    info = SymbolMarketInfo(
        symbol="BTC/USDT",
        base_asset="BTC",
        quote_asset="USDT",
        metadata={"source": "fixture"},
    )

    with pytest.raises(TypeError):
        info.metadata["source"] = "changed"  # type: ignore[index]
