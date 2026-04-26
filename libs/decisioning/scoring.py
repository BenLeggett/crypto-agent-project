"""Policy-neutral proposal validation reports.

This module checks decision-engine boundary conditions only. Account-level risk
authority remains in the supervisor/risk governor; these helpers simply produce
explicit fail-closed reasons before a proposal can move toward that path.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from hashlib import sha256
from typing import Optional, Sequence

from libs.decisioning.schemas import (
    DecisionInput,
    DecisionMode,
    ProposalRejection,
    ProposalRejectionReason,
    TradeProposal,
)


@dataclass(frozen=True)
class ProposalValidationPolicy:
    """Policy-neutral bounds for pre-risk proposal validation."""

    allowed_symbols: Sequence[str]
    max_notional: Decimal
    max_quantity: Decimal
    min_confidence: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        allowed = tuple(self.allowed_symbols)
        if not allowed:
            raise ValueError("allowed_symbols must not be empty")
        if self.max_notional <= Decimal("0"):
            raise ValueError("max_notional must be positive")
        if self.max_quantity <= Decimal("0"):
            raise ValueError("max_quantity must be positive")
        if self.min_confidence < Decimal("0") or self.min_confidence > Decimal("1"):
            raise ValueError("min_confidence must be between 0 and 1")
        object.__setattr__(self, "allowed_symbols", allowed)


@dataclass(frozen=True)
class ProposalValidationIssue:
    """Single explicit reason a proposal failed closed."""

    reason: ProposalRejectionReason
    message: str
    field: str


@dataclass(frozen=True)
class ProposalValidationReport:
    """Validation result that can be converted to replayable rejections."""

    decision_id: str
    proposal_id: Optional[str]
    passed: bool
    issues: tuple[ProposalValidationIssue, ...]

    def to_rejections(self, *, created_at_ms: int) -> tuple[ProposalRejection, ...]:
        """Convert validation issues to structured proposal rejection records."""

        rejections = []
        for issue in self.issues:
            rejection_seed = "|".join(
                [
                    self.decision_id,
                    self.proposal_id or "missing-proposal",
                    issue.reason.value,
                    issue.field,
                    issue.message,
                ]
            )
            rejection_id = "reject-" + sha256(rejection_seed.encode("utf-8")).hexdigest()[:16]
            rejections.append(
                ProposalRejection(
                    rejection_id=rejection_id,
                    decision_id=self.decision_id,
                    proposal_id=self.proposal_id,
                    reason=issue.reason,
                    message=issue.message,
                    created_at_ms=created_at_ms,
                    metadata={"field": issue.field},
                )
            )
        return tuple(rejections)


def validate_proposal_policy(
    proposal: TradeProposal,
    *,
    policy: ProposalValidationPolicy,
    decision_input: Optional[DecisionInput] = None,
    now_ms: Optional[int] = None,
) -> ProposalValidationReport:
    """Return explicit fail-closed proposal validation issues."""

    issues: list[ProposalValidationIssue] = []
    decision_id = proposal.decision_id

    if proposal.mode is DecisionMode.FUTURE_LIVE:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.MODE_NOT_ALLOWED,
                message="future live proposals are not enabled at this stage",
                field="mode",
            )
        )

    if now_ms is not None and proposal.valid_until_ms <= now_ms:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.STALE_DATA,
                message="proposal is expired",
                field="valid_until_ms",
            )
        )

    if proposal.symbol not in policy.allowed_symbols:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SYMBOL_NOT_ALLOWED,
                message="proposal symbol is not in the validation policy universe",
                field="symbol",
            )
        )

    if proposal.notional > policy.max_notional:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SIZE_INVALID,
                message="proposal notional exceeds validation policy maximum",
                field="notional",
            )
        )

    if proposal.quantity > policy.max_quantity:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SIZE_INVALID,
                message="proposal quantity exceeds validation policy maximum",
                field="quantity",
            )
        )

    if proposal.confidence < policy.min_confidence:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SCHEMA_INVALID,
                message="proposal confidence is below validation policy minimum",
                field="confidence",
            )
        )

    if not proposal.rationale.strip():
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.RATIONALE_MISSING,
                message="proposal rationale is required",
                field="rationale",
            )
        )

    if decision_input is not None:
        issues.extend(_validate_context(proposal, decision_input))

    return ProposalValidationReport(
        decision_id=decision_id,
        proposal_id=proposal.proposal_id,
        passed=not issues,
        issues=tuple(issues),
    )


def _validate_context(proposal: TradeProposal, decision_input: DecisionInput) -> tuple[ProposalValidationIssue, ...]:
    issues: list[ProposalValidationIssue] = []

    market_age_ms = decision_input.created_at_ms - decision_input.market.timestamp_ms
    if market_age_ms < 0:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.TIMESTAMP_INVALID,
                message="market timestamp cannot be after decision creation time",
                field="market.timestamp_ms",
            )
        )
    elif market_age_ms > decision_input.max_market_age_ms:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.STALE_DATA,
                message="market snapshot is stale",
                field="market.timestamp_ms",
            )
        )

    if decision_input.market.symbol not in decision_input.allowed_symbols:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SYMBOL_NOT_ALLOWED,
                message="market symbol is not in decision input allowed_symbols",
                field="allowed_symbols",
            )
        )

    if proposal.decision_id != decision_input.decision_id:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SCHEMA_INVALID,
                message="proposal decision_id must match decision input",
                field="decision_id",
            )
        )

    if proposal.run_id != decision_input.run_id:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SCHEMA_INVALID,
                message="proposal run_id must match decision input",
                field="run_id",
            )
        )

    if proposal.mode is not decision_input.mode:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.MODE_NOT_ALLOWED,
                message="proposal mode must match decision input",
                field="mode",
            )
        )

    if proposal.symbol != decision_input.market.symbol:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SYMBOL_NOT_ALLOWED,
                message="proposal symbol must match market snapshot",
                field="symbol",
            )
        )

    if proposal.symbol not in decision_input.allowed_symbols:
        issues.append(
            ProposalValidationIssue(
                reason=ProposalRejectionReason.SYMBOL_NOT_ALLOWED,
                message="proposal symbol must be allowed by decision input",
                field="allowed_symbols",
            )
        )

    return tuple(issues)


__all__ = [
    "ProposalValidationIssue",
    "ProposalValidationPolicy",
    "ProposalValidationReport",
    "validate_proposal_policy",
]
