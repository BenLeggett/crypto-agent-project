"""Deterministic trading-universe selection.

The selector is deliberately pure: callers provide configured symbols and any
market metadata they already collected elsewhere. This module never reads from
an exchange, Freqtrade runtime, filesystem, model provider, or wallet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Optional, Sequence, Tuple


class UniverseRejectionReason(str, Enum):
    """Machine-readable reasons a configured symbol was excluded."""

    EMPTY_SYMBOL = "empty_symbol"
    DUPLICATE_SYMBOL = "duplicate_symbol"
    DENYLISTED = "denylisted"
    MISSING_METADATA = "missing_metadata"
    INACTIVE_MARKET = "inactive_market"
    QUOTE_ASSET_NOT_ALLOWED = "quote_asset_not_allowed"
    BELOW_MIN_NOTIONAL = "below_min_notional"
    MAX_SYMBOLS_REACHED = "max_symbols_reached"


@dataclass(frozen=True)
class SymbolMarketInfo:
    """Optional local market metadata used by deterministic universe filters."""

    symbol: str
    base_asset: str
    quote_asset: str
    is_active: bool = True
    min_notional: Optional[Decimal] = None
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_symbol(self.symbol)
        _require_text(self.base_asset, "base_asset")
        _require_text(self.quote_asset, "quote_asset")
        if self.min_notional is not None:
            _require_decimal(self.min_notional, "min_notional")
            if self.min_notional < Decimal("0"):
                raise ValueError("min_notional must be non-negative")
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class UniverseSelectionConfig:
    """Configuration for selecting the deterministic trading universe."""

    configured_symbols: Sequence[str]
    allowed_quote_assets: Sequence[str] = ()
    denied_symbols: Sequence[str] = ()
    max_symbols: Optional[int] = None
    require_active: bool = True
    require_metadata: bool = False
    min_notional_floor: Optional[Decimal] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "configured_symbols", tuple(self.configured_symbols))
        object.__setattr__(self, "allowed_quote_assets", tuple(self.allowed_quote_assets))
        object.__setattr__(self, "denied_symbols", tuple(self.denied_symbols))
        if self.max_symbols is not None and self.max_symbols < 1:
            raise ValueError("max_symbols must be positive when provided")
        if self.min_notional_floor is not None:
            _require_decimal(self.min_notional_floor, "min_notional_floor")
            if self.min_notional_floor < Decimal("0"):
                raise ValueError("min_notional_floor must be non-negative")


@dataclass(frozen=True)
class UniverseRejection:
    """One rejected configured symbol with a stable reason."""

    symbol: str
    reason: UniverseRejectionReason
    detail: str

    def __post_init__(self) -> None:
        if self.reason is not UniverseRejectionReason.EMPTY_SYMBOL:
            _require_symbol(self.symbol)
        _require_text(self.detail, "detail")


@dataclass(frozen=True)
class UniverseSelection:
    """Selected universe plus rejected symbols for audit and operator reporting."""

    selected_symbols: Tuple[str, ...]
    rejected_symbols: Tuple[UniverseRejection, ...]

    @property
    def is_empty(self) -> bool:
        return not self.selected_symbols


def select_universe(
    config: UniverseSelectionConfig,
    market_info: Optional[Mapping[str, SymbolMarketInfo]] = None,
) -> UniverseSelection:
    """Filter configured symbols in stable config order."""
    metadata = market_info or {}
    selected: list[str] = []
    rejected: list[UniverseRejection] = []
    seen: set[str] = set()
    denied = {_canonical(symbol) for symbol in config.denied_symbols}
    allowed_quotes = {_canonical(asset) for asset in config.allowed_quote_assets}

    for raw_symbol in config.configured_symbols:
        symbol = raw_symbol.strip() if isinstance(raw_symbol, str) else ""
        canonical_symbol = _canonical(symbol)

        if not symbol:
            rejected.append(
                UniverseRejection(
                    symbol="",
                    reason=UniverseRejectionReason.EMPTY_SYMBOL,
                    detail="configured symbol is empty",
                )
            )
            continue
        if canonical_symbol in seen:
            rejected.append(
                UniverseRejection(
                    symbol=symbol,
                    reason=UniverseRejectionReason.DUPLICATE_SYMBOL,
                    detail="symbol appeared more than once in configured universe",
                )
            )
            continue
        seen.add(canonical_symbol)

        if canonical_symbol in denied:
            rejected.append(
                UniverseRejection(
                    symbol=symbol,
                    reason=UniverseRejectionReason.DENYLISTED,
                    detail="symbol is explicitly denied by universe config",
                )
            )
            continue

        info = _lookup_market_info(symbol, metadata)
        if config.require_metadata and info is None:
            rejected.append(
                UniverseRejection(
                    symbol=symbol,
                    reason=UniverseRejectionReason.MISSING_METADATA,
                    detail="metadata is required but was not provided for symbol",
                )
            )
            continue
        if config.require_active and info is not None and not info.is_active:
            rejected.append(
                UniverseRejection(
                    symbol=symbol,
                    reason=UniverseRejectionReason.INACTIVE_MARKET,
                    detail="market metadata marks symbol inactive",
                )
            )
            continue

        quote_asset = _quote_asset(symbol, info)
        if allowed_quotes and _canonical(quote_asset) not in allowed_quotes:
            rejected.append(
                UniverseRejection(
                    symbol=symbol,
                    reason=UniverseRejectionReason.QUOTE_ASSET_NOT_ALLOWED,
                    detail=f"quote asset {quote_asset!r} is not allowed",
                )
            )
            continue

        if (
            config.min_notional_floor is not None
            and info is not None
            and info.min_notional is not None
            and info.min_notional < config.min_notional_floor
        ):
            rejected.append(
                UniverseRejection(
                    symbol=symbol,
                    reason=UniverseRejectionReason.BELOW_MIN_NOTIONAL,
                    detail="market min_notional is below configured floor",
                )
            )
            continue

        if config.max_symbols is not None and len(selected) >= config.max_symbols:
            rejected.append(
                UniverseRejection(
                    symbol=symbol,
                    reason=UniverseRejectionReason.MAX_SYMBOLS_REACHED,
                    detail="symbol was excluded after max_symbols was reached",
                )
            )
            continue

        selected.append(symbol)

    return UniverseSelection(
        selected_symbols=tuple(selected),
        rejected_symbols=tuple(rejected),
    )


def _lookup_market_info(
    symbol: str,
    market_info: Mapping[str, SymbolMarketInfo],
) -> Optional[SymbolMarketInfo]:
    if symbol in market_info:
        return market_info[symbol]
    canonical_symbol = _canonical(symbol)
    for candidate_symbol, info in market_info.items():
        if _canonical(candidate_symbol) == canonical_symbol:
            return info
    return None


def _quote_asset(symbol: str, info: Optional[SymbolMarketInfo]) -> str:
    if info is not None:
        return info.quote_asset
    if "/" in symbol:
        return symbol.rsplit("/", 1)[1]
    return ""


def _canonical(value: str) -> str:
    return value.strip().upper()


def _require_symbol(symbol: str) -> None:
    _require_text(symbol, "symbol")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")


def _require_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")


__all__ = [
    "SymbolMarketInfo",
    "UniverseRejection",
    "UniverseRejectionReason",
    "UniverseSelection",
    "UniverseSelectionConfig",
    "select_universe",
]
