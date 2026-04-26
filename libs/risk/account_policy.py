"""Account-level deterministic risk policy.

This module is the shared pre-execution risk boundary for paper and future
live modes. It evaluates structured proposals only; it never places orders,
calls exchanges, reads credentials, or mutates live configuration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Sequence

from libs.decisioning.schemas import DecisionMode, ProposalAction, TradeProposal
from libs.risk.drawdown_rules import DrawdownLimits, DrawdownState, evaluate_drawdown
from libs.risk.position_limits import OpenPosition, PositionLimitConfig, evaluate_position_limits

RISK_POLICY_SCHEMA_VERSION = "risk_policy_decision.v1"


@dataclass(frozen=True)
class AccountRiskLimits:
    """Hard account-level risk bounds owned by the deterministic governor."""

    allowed_symbols: tuple[str, ...]
    position_limits: PositionLimitConfig
    drawdown_limits: DrawdownLimits
    allow_future_live: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_symbols:
            raise ValueError("allowed_symbols must not be empty")
        for symbol in self.allowed_symbols:
            if not symbol.strip():
                raise ValueError("allowed_symbols must contain non-empty symbols")


@dataclass(frozen=True)
class AccountRiskState:
    """Runtime account state supplied by the supervisor/reconciliation layer."""

    drawdown: DrawdownState
    open_positions: tuple[OpenPosition, ...] = ()
    entries_frozen: bool = False
    kill_switch_active: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "open_positions", tuple(self.open_positions))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class RiskPolicyIssue:
    """One stable reason a proposal was vetoed."""

    code: str
    message: str
    severity: str = "veto"

    def to_record(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(frozen=True)
class RiskPolicyDecision:
    """Deterministic allow/veto decision for a proposal."""

    schema_version: str
    proposal_id: str
    decision_id: str
    run_id: str
    allowed: bool
    issues: tuple[RiskPolicyIssue, ...]
    metadata: Mapping[str, str] = field(default_factory=dict)

    @property
    def primary_reason(self) -> str:
        return "allowed" if self.allowed else self.issues[0].code

    def to_record(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "proposal_id": self.proposal_id,
            "decision_id": self.decision_id,
            "run_id": self.run_id,
            "allowed": self.allowed,
            "primary_reason": self.primary_reason,
            "issues": [issue.to_record() for issue in self.issues],
            "metadata": dict(self.metadata),
        }


class AccountRiskPolicy:
    """Evaluate deterministic account policy for structured proposals."""

    def __init__(self, limits: AccountRiskLimits) -> None:
        self.limits = limits

    def evaluate(self, proposal: TradeProposal, state: AccountRiskState) -> RiskPolicyDecision:
        if not isinstance(proposal, TradeProposal):
            raise TypeError("proposal must be a TradeProposal")
        issues: list[RiskPolicyIssue] = []

        if proposal.mode is DecisionMode.FUTURE_LIVE and not self.limits.allow_future_live:
            issues.append(_issue("mode_not_allowed", "future live proposals are not enabled"))
        if state.kill_switch_active:
            issues.append(_issue("kill_switch_active", "kill switch is active"))
        if proposal.symbol not in self.limits.allowed_symbols:
            issues.append(_issue("symbol_not_allowed", "proposal symbol is outside allowed markets"))

        if proposal.action is ProposalAction.ENTER:
            issues.extend(self._entry_issues(proposal, state))

        metadata = {
            "proposal_symbol": proposal.symbol,
            "proposal_action": proposal.action.value,
            "proposal_mode": proposal.mode.value,
        }
        return RiskPolicyDecision(
            schema_version=RISK_POLICY_SCHEMA_VERSION,
            proposal_id=proposal.proposal_id,
            decision_id=proposal.decision_id,
            run_id=proposal.run_id,
            allowed=not issues,
            issues=tuple(issues),
            metadata=metadata,
        )

    def _entry_issues(self, proposal: TradeProposal, state: AccountRiskState) -> tuple[RiskPolicyIssue, ...]:
        issues: list[RiskPolicyIssue] = []
        if state.entries_frozen:
            issues.append(_issue("entries_frozen", "new entries are frozen"))

        drawdown = evaluate_drawdown(state.drawdown, self.limits.drawdown_limits)
        if not drawdown.passed:
            issues.append(_issue(drawdown.reason, "drawdown limit exceeded"))

        position = evaluate_position_limits(
            symbol=proposal.symbol,
            proposal_notional=proposal.notional,
            open_positions=state.open_positions,
            limits=self.limits.position_limits,
        )
        if not position.passed:
            issues.append(_issue(position.reason, "position exposure limit exceeded"))
        return tuple(issues)


def evaluate_account_policy(
    proposal: TradeProposal,
    *,
    limits: AccountRiskLimits,
    state: AccountRiskState,
) -> RiskPolicyDecision:
    """Convenience wrapper for evaluating a single proposal."""

    return AccountRiskPolicy(limits).evaluate(proposal, state)


def _issue(code: str, message: str) -> RiskPolicyIssue:
    return RiskPolicyIssue(code=code, message=message)


__all__ = [
    "RISK_POLICY_SCHEMA_VERSION",
    "AccountRiskLimits",
    "AccountRiskPolicy",
    "AccountRiskState",
    "RiskPolicyDecision",
    "RiskPolicyIssue",
    "evaluate_account_policy",
]
