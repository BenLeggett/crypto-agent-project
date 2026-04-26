"""Deterministic supervisor service.

The supervisor is the application-owned boundary around account-level risk
governance. It evaluates structured proposals and operational state only; it
does not place orders, call exchanges, read secrets, or enable live execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from apps.supervisor.health import HealthStatus, SupervisorHealth, build_supervisor_health
from libs.decisioning.schemas import TradeProposal
from libs.risk import AccountRiskLimits, AccountRiskPolicy, AccountRiskState, FreezeState, RiskPolicyDecision

SUPERVISOR_EVALUATION_SCHEMA_VERSION = "supervisor_policy_evaluation.v1"


@dataclass(frozen=True)
class SupervisorConfig:
    """Runtime supervisor configuration supplied by local config or tests."""

    account_limits: AccountRiskLimits
    service_name: str = "supervisor"
    risk_enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.account_limits, AccountRiskLimits):
            raise TypeError("account_limits must be an AccountRiskLimits")
        if not self.service_name.strip():
            raise ValueError("service_name must be non-empty")
        if not self.risk_enabled:
            raise ValueError("deterministic risk governor must remain enabled")


@dataclass(frozen=True)
class SupervisorEvaluation:
    """Versioned proposal evaluation emitted by the supervisor."""

    risk_decision: RiskPolicyDecision
    health: SupervisorHealth
    accepted: bool
    schema_version: str = SUPERVISOR_EVALUATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SUPERVISOR_EVALUATION_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {SUPERVISOR_EVALUATION_SCHEMA_VERSION!r}")
        if not isinstance(self.risk_decision, RiskPolicyDecision):
            raise TypeError("risk_decision must be a RiskPolicyDecision")
        if not isinstance(self.health, SupervisorHealth):
            raise TypeError("health must be a SupervisorHealth")

    @property
    def proposal_id(self) -> str:
        return self.risk_decision.proposal_id

    @property
    def decision_id(self) -> str:
        return self.risk_decision.decision_id

    @property
    def run_id(self) -> str:
        return self.risk_decision.run_id

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "accepted": self.accepted,
            "risk_decision": self.risk_decision.to_record(),
            "health": self.health.to_record(),
        }


class SupervisorService:
    """Evaluate proposals through the deterministic account risk policy."""

    def __init__(self, config: SupervisorConfig) -> None:
        if not isinstance(config, SupervisorConfig):
            raise TypeError("config must be a SupervisorConfig")
        self.config = config
        self._policy = AccountRiskPolicy(config.account_limits)

    def evaluate_proposal(self, proposal: TradeProposal, state: AccountRiskState) -> SupervisorEvaluation:
        """Return the supervisor's authoritative pre-execution decision."""

        if not isinstance(proposal, TradeProposal):
            raise TypeError("proposal must be a TradeProposal")
        if not isinstance(state, AccountRiskState):
            raise TypeError("state must be an AccountRiskState")

        risk_decision = self._policy.evaluate(proposal, state)
        health = self.health(state)
        accepted = risk_decision.allowed and health.status is not HealthStatus.STOPPED
        return SupervisorEvaluation(
            risk_decision=risk_decision,
            health=health,
            accepted=accepted,
        )

    def evaluate_proposal_with_controls(
        self,
        proposal: TradeProposal,
        state: AccountRiskState,
        controls: FreezeState,
    ) -> SupervisorEvaluation:
        """Evaluate a proposal after applying supervisor control state."""

        return self.evaluate_proposal(proposal, account_state_with_controls(state, controls))

    def health(self, state: AccountRiskState) -> SupervisorHealth:
        """Evaluate local supervisor health from deterministic state."""

        return build_supervisor_health(
            state=state,
            limits=self.config.account_limits,
            policy_loaded=True,
        )


def account_state_with_controls(state: AccountRiskState, controls: FreezeState) -> AccountRiskState:
    """Return account state with freeze and kill-switch controls applied."""

    if not isinstance(state, AccountRiskState):
        raise TypeError("state must be an AccountRiskState")
    if not isinstance(controls, FreezeState):
        raise TypeError("controls must be a FreezeState")
    return AccountRiskState(
        drawdown=state.drawdown,
        open_positions=state.open_positions,
        entries_frozen=controls.entries_frozen,
        kill_switch_active=controls.kill_switch_active,
        metadata={
            **dict(state.metadata),
            "control_command_id": controls.command_id or "",
            "control_reason": controls.reason,
            "flatten_requested": str(controls.flatten_requested).lower(),
        },
    )


__all__ = [
    "SUPERVISOR_EVALUATION_SCHEMA_VERSION",
    "SupervisorConfig",
    "SupervisorEvaluation",
    "SupervisorService",
    "account_state_with_controls",
]
