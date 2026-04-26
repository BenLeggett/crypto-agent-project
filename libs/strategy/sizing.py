"""Pure deterministic position sizing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import Optional

from libs.strategy.interfaces import PositionSize, SizingInput, StrategyContext


@dataclass(frozen=True)
class PositionSizingConfig:
    """Bounds applied by deterministic strategy sizing before risk governor review."""

    min_quantity: Decimal = Decimal("0")
    quantity_step: Decimal = Decimal("0.00000001")
    min_notional: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        _require_non_negative_decimal(self.min_quantity, "min_quantity")
        _require_positive_decimal(self.quantity_step, "quantity_step")
        _require_non_negative_decimal(self.min_notional, "min_notional")


@dataclass(frozen=True)
class SizingResult:
    """Intermediate deterministic sizing math for tests and reporting."""

    raw_quantity: Decimal
    capped_quantity: Decimal
    stepped_quantity: Decimal
    per_unit_risk: Decimal
    risk_budget: Decimal
    max_notional_quantity: Decimal


class DeterministicPositionSizer:
    """Size positions from equity risk, stop distance, and max notional bounds."""

    def __init__(self, config: Optional[PositionSizingConfig] = None) -> None:
        self.config = config or PositionSizingConfig()

    def size(self, sizing_input: SizingInput, context: StrategyContext) -> PositionSize:
        result = calculate_position_size(sizing_input, self.config)
        notional = result.stepped_quantity * sizing_input.entry_price
        risk_amount = result.stepped_quantity * result.per_unit_risk
        if result.stepped_quantity < self.config.min_quantity or notional < self.config.min_notional:
            quantity = Decimal("0")
            notional = Decimal("0")
            risk_amount = Decimal("0")
            reason = "position below configured minimums"
        else:
            quantity = result.stepped_quantity
            reason = "position sized from risk budget and max notional"

        return PositionSize(
            symbol=sizing_input.symbol,
            side=sizing_input.side,
            quantity=quantity,
            notional=_money(notional),
            risk_amount=_money(risk_amount),
            reason=reason,
            metadata={
                "run_id": context.run_id,
                "config_hash": context.config_hash,
                "raw_quantity": _decimal(result.raw_quantity),
                "capped_quantity": _decimal(result.capped_quantity),
                "stepped_quantity": _decimal(result.stepped_quantity),
                "per_unit_risk": _decimal(result.per_unit_risk),
                "risk_budget": str(_money(result.risk_budget)),
                "max_notional_quantity": _decimal(result.max_notional_quantity),
                "quantity_step": _decimal(self.config.quantity_step),
            },
        )


def calculate_position_size(
    sizing_input: SizingInput,
    config: Optional[PositionSizingConfig] = None,
) -> SizingResult:
    """Calculate deterministic sizing intermediates without side effects."""
    sizing_config = config or PositionSizingConfig()
    per_unit_risk = abs(sizing_input.entry_price - sizing_input.stop_price)
    if per_unit_risk <= Decimal("0"):
        raise ValueError("per_unit_risk must be positive")

    risk_budget = sizing_input.equity * sizing_input.risk_fraction
    raw_quantity = risk_budget / per_unit_risk
    max_notional_quantity = sizing_input.max_position_value / sizing_input.entry_price
    capped_quantity = min(raw_quantity, max_notional_quantity)
    stepped_quantity = floor_to_step(capped_quantity, sizing_config.quantity_step)

    return SizingResult(
        raw_quantity=raw_quantity,
        capped_quantity=capped_quantity,
        stepped_quantity=stepped_quantity,
        per_unit_risk=per_unit_risk,
        risk_budget=risk_budget,
        max_notional_quantity=max_notional_quantity,
    )


def size_position(
    sizing_input: SizingInput,
    context: StrategyContext,
    config: Optional[PositionSizingConfig] = None,
) -> PositionSize:
    return DeterministicPositionSizer(config).size(sizing_input, context)


def floor_to_step(value: Decimal, step: Decimal) -> Decimal:
    _require_non_negative_decimal(value, "value")
    _require_positive_decimal(step, "step")
    return (value / step).to_integral_value(rounding=ROUND_DOWN) * step


def _decimal(value: Decimal) -> str:
    return str(value.normalize())


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def _require_positive_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value <= Decimal("0"):
        raise ValueError(f"{field_name} must be positive")


def _require_non_negative_decimal(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value < Decimal("0"):
        raise ValueError(f"{field_name} must be non-negative")


__all__ = [
    "DeterministicPositionSizer",
    "PositionSizingConfig",
    "SizingResult",
    "calculate_position_size",
    "floor_to_step",
    "size_position",
]
