"""Deterministic supervisor health records.

Health checks here are intentionally local and state-driven. They do not call
exchanges, notifiers, models, or wallets; later tasks can feed reconciliation
or alert state into this same record shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from libs.risk import AccountRiskLimits, AccountRiskState, evaluate_drawdown

SUPERVISOR_HEALTH_SCHEMA_VERSION = "supervisor_health.v1"


class HealthStatus(str, Enum):
    """Supervisor health severity."""

    OK = "ok"
    DEGRADED = "degraded"
    STOPPED = "stopped"


@dataclass(frozen=True)
class HealthCheck:
    """One machine-readable supervisor health check."""

    name: str
    status: HealthStatus
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("health check name must be non-empty")
        if not isinstance(self.status, HealthStatus):
            raise TypeError("health check status must be a HealthStatus")
        if not self.message.strip():
            raise ValueError("health check message must be non-empty")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))

    def to_record(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class SupervisorHealth:
    """Aggregated supervisor health for operator updates and later journaling."""

    status: HealthStatus
    checks: tuple[HealthCheck, ...]
    schema_version: str = SUPERVISOR_HEALTH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUPERVISOR_HEALTH_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SUPERVISOR_HEALTH_SCHEMA_VERSION!r}")
        if not isinstance(self.status, HealthStatus):
            raise TypeError("status must be a HealthStatus")
        checks = tuple(self.checks)
        if not checks:
            raise ValueError("supervisor health requires at least one check")
        object.__setattr__(self, "checks", checks)

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status.value,
            "checks": [check.to_record() for check in self.checks],
        }


def build_supervisor_health(
    *,
    state: AccountRiskState,
    limits: AccountRiskLimits,
    policy_loaded: bool = True,
) -> SupervisorHealth:
    """Build local health from deterministic risk-governor state."""

    if not isinstance(state, AccountRiskState):
        raise TypeError("state must be an AccountRiskState")
    if not isinstance(limits, AccountRiskLimits):
        raise TypeError("limits must be an AccountRiskLimits")

    checks = [
        _policy_check(policy_loaded),
        _drawdown_check(state, limits),
        _entry_freeze_check(state),
        _kill_switch_check(state),
    ]
    return SupervisorHealth(status=_overall_status(checks), checks=tuple(checks))


def _policy_check(policy_loaded: bool) -> HealthCheck:
    if policy_loaded:
        return HealthCheck("risk_policy", HealthStatus.OK, "deterministic risk policy is loaded")
    return HealthCheck("risk_policy", HealthStatus.STOPPED, "deterministic risk policy is unavailable")


def _drawdown_check(state: AccountRiskState, limits: AccountRiskLimits) -> HealthCheck:
    drawdown = evaluate_drawdown(state.drawdown, limits.drawdown_limits)
    if drawdown.passed:
        return HealthCheck(
            "drawdown",
            HealthStatus.OK,
            "drawdown is within configured limits",
            drawdown.to_record(),
        )
    return HealthCheck(
        "drawdown",
        HealthStatus.DEGRADED,
        "drawdown limit is exceeded; new entries should be vetoed",
        drawdown.to_record(),
    )


def _entry_freeze_check(state: AccountRiskState) -> HealthCheck:
    if state.entries_frozen:
        return HealthCheck("entries", HealthStatus.DEGRADED, "new entries are frozen")
    return HealthCheck("entries", HealthStatus.OK, "new entries are not frozen")


def _kill_switch_check(state: AccountRiskState) -> HealthCheck:
    if state.kill_switch_active:
        return HealthCheck("kill_switch", HealthStatus.STOPPED, "kill switch is active")
    return HealthCheck("kill_switch", HealthStatus.OK, "kill switch is inactive")


def _overall_status(checks: Sequence[HealthCheck]) -> HealthStatus:
    severities = {HealthStatus.OK: 0, HealthStatus.DEGRADED: 1, HealthStatus.STOPPED: 2}
    return max((check.status for check in checks), key=lambda status: severities[status])


__all__ = [
    "SUPERVISOR_HEALTH_SCHEMA_VERSION",
    "HealthCheck",
    "HealthStatus",
    "SupervisorHealth",
    "build_supervisor_health",
]
