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
from libs.event_packets import EventPacket, build_risk_decision_packet
from libs.journal import JournalRecord, JournalRecordType
from libs.risk import AccountRiskLimits, AccountRiskPolicy, AccountRiskState, FreezeState, RiskPolicyDecision

SUPERVISOR_EVALUATION_SCHEMA_VERSION = "supervisor_policy_evaluation.v1"


@dataclass(frozen=True)
class SupervisorConfig:
    """Runtime supervisor configuration supplied by local config or tests."""

    account_limits: AccountRiskLimits
    service_name: str = "supervisor"
    config_hash: str = "supervisor-local"
    risk_enabled: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.account_limits, AccountRiskLimits):
            raise TypeError("account_limits must be an AccountRiskLimits")
        if not self.service_name.strip():
            raise ValueError("service_name must be non-empty")
        if not self.config_hash.strip():
            raise ValueError("config_hash must be non-empty")
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


@dataclass(frozen=True)
class SupervisorAuditArtifacts:
    """Local audit artifacts emitted by a supervisor evaluation."""

    evaluation: SupervisorEvaluation
    journal_records: tuple[JournalRecord, ...]
    event_packets: tuple[EventPacket, ...]

    def to_record(self) -> dict[str, Any]:
        return {
            "evaluation": self.evaluation.to_record(),
            "journal_records": [record.to_record() for record in self.journal_records],
            "event_packets": [packet.to_record() for packet in self.event_packets],
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

    def evaluate_proposal_with_audit(
        self,
        proposal: TradeProposal,
        state: AccountRiskState,
    ) -> SupervisorAuditArtifacts:
        """Evaluate a proposal and build local journal/packet artifacts."""

        return self.audit_evaluation(self.evaluate_proposal(proposal, state))

    def evaluate_proposal_with_controls(
        self,
        proposal: TradeProposal,
        state: AccountRiskState,
        controls: FreezeState,
    ) -> SupervisorEvaluation:
        """Evaluate a proposal after applying supervisor control state."""

        return self.evaluate_proposal(proposal, account_state_with_controls(state, controls))

    def evaluate_proposal_with_controls_and_audit(
        self,
        proposal: TradeProposal,
        state: AccountRiskState,
        controls: FreezeState,
    ) -> SupervisorAuditArtifacts:
        """Evaluate a proposal with controls and build local audit artifacts."""

        return self.audit_evaluation(self.evaluate_proposal_with_controls(proposal, state, controls))

    def health(self, state: AccountRiskState) -> SupervisorHealth:
        """Evaluate local supervisor health from deterministic state."""

        return build_supervisor_health(
            state=state,
            limits=self.config.account_limits,
            policy_loaded=True,
        )

    def audit_evaluation(self, evaluation: SupervisorEvaluation) -> SupervisorAuditArtifacts:
        """Build journal records and packets for an existing evaluation."""

        if not isinstance(evaluation, SupervisorEvaluation):
            raise TypeError("evaluation must be a SupervisorEvaluation")

        risk_record = evaluation.risk_decision.to_record()
        journal_record = JournalRecord(
            record_id=f"risk-decision-{evaluation.run_id}-{evaluation.decision_id}",
            run_id=evaluation.run_id,
            created_at_ms=_risk_decision_created_at_ms(evaluation.risk_decision),
            record_type=JournalRecordType.RISK_DECISION,
            source=self.config.service_name,
            config_hash=self.config.config_hash,
            payload=evaluation.to_record(),
            metadata={
                "proposal_id": evaluation.proposal_id,
                "accepted": str(evaluation.accepted).lower(),
                "primary_reason": evaluation.risk_decision.primary_reason,
            },
        )
        packet = build_risk_decision_packet(
            run_id=evaluation.run_id,
            decision_id=evaluation.decision_id,
            occurred_at_ms=_risk_decision_created_at_ms(evaluation.risk_decision),
            risk_decision=risk_record,
            allowed=evaluation.accepted,
            source=self.config.service_name,
        )
        return SupervisorAuditArtifacts(
            evaluation=evaluation,
            journal_records=(journal_record,),
            event_packets=(packet,),
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


def _risk_decision_created_at_ms(decision: RiskPolicyDecision) -> int:
    value = decision.metadata.get("created_at_ms", "")
    return int(value) if value else 0


__all__ = [
    "SUPERVISOR_EVALUATION_SCHEMA_VERSION",
    "SupervisorAuditArtifacts",
    "SupervisorConfig",
    "SupervisorEvaluation",
    "SupervisorService",
    "account_state_with_controls",
]
