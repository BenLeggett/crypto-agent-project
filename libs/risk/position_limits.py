"""Pure deterministic position and exposure limit checks."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

from libs.strategy.interfaces import TradeSide


@dataclass(frozen=True)
class PositionLimitConfig:
    """Hard account-level exposure bounds."""

    max_order_notional: Decimal
    max_symbol_exposure: Decimal
    max_total_exposure: Decimal

    def __post_init__(self) -> None:
        _require_positive(self.max_order_notional, "max_order_notional")
        _require_positive(self.max_symbol_exposure, "max_symbol_exposure")
        _require_positive(self.max_total_exposure, "max_total_exposure")
        if self.max_symbol_exposure > self.max_total_exposure:
            raise ValueError("max_symbol_exposure must not exceed max_total_exposure")


@dataclass(frozen=True)
class OpenPosition:
    """Current known exposure for one symbol and side."""

    symbol: str
    side: TradeSide
    notional: Decimal

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must be non-empty")
        if not isinstance(self.side, TradeSide):
            raise TypeError("side must be a TradeSide")
        _require_non_negative(self.notional, "notional")


@dataclass(frozen=True)
class PositionLimitCheck:
    """Position-limit outcome with projected exposure details."""

    passed: bool
    reason: str
    projected_symbol_exposure: Decimal
    projected_total_exposure: Decimal

    def to_record(self) -> dict[str, str | bool]:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "projected_symbol_exposure": _decimal_text(self.projected_symbol_exposure),
            "projected_total_exposure": _decimal_text(self.projected_total_exposure),
        }


def total_exposure(positions: Sequence[OpenPosition]) -> Decimal:
    """Return absolute account exposure across known open positions."""

    return sum((position.notional for position in positions), Decimal("0"))


def symbol_exposure(positions: Sequence[OpenPosition], symbol: str) -> Decimal:
    """Return absolute exposure for one symbol across sides."""

    return sum((position.notional for position in positions if position.symbol == symbol), Decimal("0"))


def evaluate_position_limits(
    *,
    symbol: str,
    proposal_notional: Decimal,
    open_positions: Sequence[OpenPosition],
    limits: PositionLimitConfig,
) -> PositionLimitCheck:
    """Evaluate per-order, per-symbol, and total projected exposure."""

    if not symbol.strip():
        raise ValueError("symbol must be non-empty")
    _require_positive(proposal_notional, "proposal_notional")

    projected_symbol = symbol_exposure(open_positions, symbol) + proposal_notional
    projected_total = total_exposure(open_positions) + proposal_notional
    if proposal_notional > limits.max_order_notional:
        return PositionLimitCheck(False, "max_order_notional_exceeded", projected_symbol, projected_total)
    if projected_symbol > limits.max_symbol_exposure:
        return PositionLimitCheck(False, "max_symbol_exposure_exceeded", projected_symbol, projected_total)
    if projected_total > limits.max_total_exposure:
        return PositionLimitCheck(False, "max_total_exposure_exceeded", projected_symbol, projected_total)
    return PositionLimitCheck(True, "position_limits_within_bounds", projected_symbol, projected_total)


def _require_positive(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value <= Decimal("0"):
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


def _decimal_text(value: Decimal) -> str:
    return format(value.normalize(), "f")


__all__ = [
    "OpenPosition",
    "PositionLimitCheck",
    "PositionLimitConfig",
    "evaluate_position_limits",
    "symbol_exposure",
    "total_exposure",
]
