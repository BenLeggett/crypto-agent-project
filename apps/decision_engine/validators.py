"""Validation helpers for decision-engine schema boundaries."""

from __future__ import annotations

from typing import Optional

from libs.decisioning.schemas import (
    DecisionInput,
    DecisionMode,
    DecisionSchemaError,
    NoTradeDecision,
    ProposalRejectionReason,
    TradeProposal,
)
from libs.decisioning.scoring import (
    ProposalValidationPolicy,
    ProposalValidationReport,
    validate_proposal_policy,
)


class DecisionValidationError(DecisionSchemaError):
    """Raised when a decision record fails policy-neutral validation."""


def validate_decision_input(decision_input: DecisionInput) -> DecisionInput:
    """Validate a canonical decision input and fail closed on stale snapshots."""

    if not isinstance(decision_input, DecisionInput):
        raise TypeError("decision_input must be a DecisionInput")
    if decision_input.market.symbol not in decision_input.allowed_symbols:
        raise DecisionValidationError("market symbol must be in allowed_symbols")
    age_ms = decision_input.created_at_ms - decision_input.market.timestamp_ms
    if age_ms < 0:
        raise DecisionValidationError("market timestamp cannot be after decision creation time")
    if age_ms > decision_input.max_market_age_ms:
        raise DecisionValidationError("market snapshot is stale")
    return decision_input


def validate_trade_proposal(
    proposal: TradeProposal,
    *,
    decision_input: Optional[DecisionInput] = None,
    policy: Optional[ProposalValidationPolicy] = None,
    now_ms: Optional[int] = None,
) -> TradeProposal:
    """Validate proposal shape and context before risk-governor review."""

    if not isinstance(proposal, TradeProposal):
        raise TypeError("proposal must be a TradeProposal")
    if policy is not None:
        report = build_trade_proposal_validation_report(
            proposal,
            decision_input=decision_input,
            policy=policy,
            now_ms=now_ms,
        )
        if not report.passed:
            first_issue = report.issues[0]
            raise DecisionValidationError(first_issue.message)
        return proposal
    if proposal.mode is DecisionMode.FUTURE_LIVE:
        raise DecisionValidationError("future live proposals are not enabled at this stage")
    if now_ms is not None and proposal.valid_until_ms <= now_ms:
        raise DecisionValidationError("proposal is expired")
    if decision_input is not None:
        validate_decision_input(decision_input)
        if proposal.decision_id != decision_input.decision_id:
            raise DecisionValidationError("proposal decision_id must match decision input")
        if proposal.run_id != decision_input.run_id:
            raise DecisionValidationError("proposal run_id must match decision input")
        if proposal.mode is not decision_input.mode:
            raise DecisionValidationError("proposal mode must match decision input")
        if proposal.symbol != decision_input.market.symbol:
            raise DecisionValidationError("proposal symbol must match market snapshot")
        if proposal.symbol not in decision_input.allowed_symbols:
            raise DecisionValidationError("proposal symbol must be allowed")
    return proposal


def build_trade_proposal_validation_report(
    proposal: TradeProposal,
    *,
    policy: ProposalValidationPolicy,
    decision_input: Optional[DecisionInput] = None,
    now_ms: Optional[int] = None,
) -> ProposalValidationReport:
    """Build an explicit validation report for replayable fail-closed handling."""

    if not isinstance(proposal, TradeProposal):
        raise TypeError("proposal must be a TradeProposal")
    return validate_proposal_policy(
        proposal,
        decision_input=decision_input,
        policy=policy,
        now_ms=now_ms,
    )


def validate_no_trade_decision(
    no_trade: NoTradeDecision,
    *,
    decision_input: Optional[DecisionInput] = None,
) -> NoTradeDecision:
    """Validate structured no-trade records used for replay and reporting."""

    if not isinstance(no_trade, NoTradeDecision):
        raise TypeError("no_trade must be a NoTradeDecision")
    if no_trade.mode is DecisionMode.FUTURE_LIVE:
        raise DecisionValidationError("future live decisions are not enabled at this stage")
    if decision_input is not None:
        validate_decision_input(decision_input)
        if no_trade.decision_id != decision_input.decision_id:
            raise DecisionValidationError("no-trade decision_id must match decision input")
        if no_trade.run_id != decision_input.run_id:
            raise DecisionValidationError("no-trade run_id must match decision input")
        if no_trade.mode is not decision_input.mode:
            raise DecisionValidationError("no-trade mode must match decision input")
        if no_trade.symbol != decision_input.market.symbol:
            raise DecisionValidationError("no-trade symbol must match market snapshot")
    return no_trade


def rejection_reason_for_error(error: Exception) -> ProposalRejectionReason:
    """Map validation failures to a stable rejection reason."""

    message = str(error).lower()
    if "stale" in message or "expired" in message:
        return ProposalRejectionReason.STALE_DATA
    if "timestamp" in message or "created_at" in message or "valid_until" in message:
        return ProposalRejectionReason.TIMESTAMP_INVALID
    if "symbol" in message:
        return ProposalRejectionReason.SYMBOL_NOT_ALLOWED
    if "quantity" in message or "notional" in message or "size" in message:
        return ProposalRejectionReason.SIZE_INVALID
    if "price" in message:
        return ProposalRejectionReason.PRICE_INVALID
    if "rationale" in message:
        return ProposalRejectionReason.RATIONALE_MISSING
    if "mode" in message or "live" in message:
        return ProposalRejectionReason.MODE_NOT_ALLOWED
    return ProposalRejectionReason.SCHEMA_INVALID


__all__ = [
    "DecisionValidationError",
    "build_trade_proposal_validation_report",
    "rejection_reason_for_error",
    "validate_decision_input",
    "validate_no_trade_decision",
    "validate_trade_proposal",
]
