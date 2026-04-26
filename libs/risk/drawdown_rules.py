"""Pure deterministic drawdown checks for the risk governor."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional


@dataclass(frozen=True)
class DrawdownLimits:
    """Account drawdown limits used before allowing new entries."""

    max_peak_drawdown: Decimal
    max_daily_drawdown: Decimal

    def __post_init__(self) -> None:
        _require_ratio(self.max_peak_drawdown, "max_peak_drawdown")
        _require_ratio(self.max_daily_drawdown, "max_daily_drawdown")


@dataclass(frozen=True)
class DrawdownState:
    """Equity values needed for deterministic drawdown evaluation."""

    current_equity: Decimal
    peak_equity: Decimal
    day_start_equity: Decimal

    def __post_init__(self) -> None:
        _require_positive(self.current_equity, "current_equity")
        _require_positive(self.peak_equity, "peak_equity")
        _require_positive(self.day_start_equity, "day_start_equity")


@dataclass(frozen=True)
class DrawdownCheck:
    """Drawdown status with stable reason fields for logging and replay."""

    passed: bool
    peak_drawdown: Decimal
    daily_drawdown: Decimal
    reason: str

    def to_record(self) -> dict[str, str | bool]:
        return {
            "passed": self.passed,
            "peak_drawdown": _decimal_text(self.peak_drawdown),
            "daily_drawdown": _decimal_text(self.daily_drawdown),
            "reason": self.reason,
        }


def calculate_drawdown(current_equity: Decimal, reference_equity: Decimal) -> Decimal:
    """Return non-negative drawdown ratio from a reference equity value."""

    _require_positive(current_equity, "current_equity")
    _require_positive(reference_equity, "reference_equity")
    if current_equity >= reference_equity:
        return Decimal("0")
    return (reference_equity - current_equity) / reference_equity


def evaluate_drawdown(state: DrawdownState, limits: DrawdownLimits) -> DrawdownCheck:
    """Evaluate peak and daily drawdown limits."""

    peak_drawdown = calculate_drawdown(state.current_equity, state.peak_equity)
    daily_drawdown = calculate_drawdown(state.current_equity, state.day_start_equity)
    if peak_drawdown > limits.max_peak_drawdown:
        return DrawdownCheck(
            passed=False,
            peak_drawdown=peak_drawdown,
            daily_drawdown=daily_drawdown,
            reason="peak_drawdown_exceeded",
        )
    if daily_drawdown > limits.max_daily_drawdown:
        return DrawdownCheck(
            passed=False,
            peak_drawdown=peak_drawdown,
            daily_drawdown=daily_drawdown,
            reason="daily_drawdown_exceeded",
        )
    return DrawdownCheck(
        passed=True,
        peak_drawdown=peak_drawdown,
        daily_drawdown=daily_drawdown,
        reason="drawdown_within_limits",
    )


def _require_positive(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value <= Decimal("0"):
        raise ValueError(f"{field_name} must be positive")


def _require_ratio(value: Decimal, field_name: str) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name} must be a Decimal")
    if value < Decimal("0") or value > Decimal("1"):
        raise ValueError(f"{field_name} must be between 0 and 1")


def _decimal_text(value: Optional[Decimal]) -> str:
    if value is None:
        return ""
    return format(value.normalize(), "f")


__all__ = [
    "DrawdownCheck",
    "DrawdownLimits",
    "DrawdownState",
    "calculate_drawdown",
    "evaluate_drawdown",
]
