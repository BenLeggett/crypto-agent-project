"""Deterministic conversion rules from strategy snapshots to proposals."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Sequence

from libs.decisioning.schemas import (
    DecisionInput,
    DecisionMode,
    DecisionOutput,
    MarketSnapshot,
    NoTradeDecision,
    NoTradeReason,
    OrderIntentType,
    ProposalAction,
    SignalSource,
    TradeProposal,
)
from libs.strategy.interfaces import EntryDecision, StrategySnapshot
from libs.strategy.signal_snapshot import SNAPSHOT_SCHEMA_VERSION, serialize_strategy_snapshot


@dataclass(frozen=True)
class DeterministicProposalConfig:
    """Configuration for deterministic snapshot-to-proposal conversion."""

    allowed_symbols: tuple[str, ...]
    mode: DecisionMode = DecisionMode.PAPER
    order_type: OrderIntentType = OrderIntentType.LIMIT
    proposal_ttl_ms: int = 300_000
    max_market_age_ms: int = 300_000

    def __post_init__(self) -> None:
        if not self.allowed_symbols:
            raise ValueError("allowed_symbols must not be empty")
        if self.proposal_ttl_ms <= 0:
            raise ValueError("proposal_ttl_ms must be positive")
        if self.max_market_age_ms <= 0:
            raise ValueError("max_market_age_ms must be positive")


@dataclass(frozen=True)
class DeterministicDecisionResult:
    """Decision input plus the deterministic output built from it."""

    decision_input: DecisionInput
    output: DecisionOutput

    def to_record(self) -> dict:
        return {
            "decision_input": self.decision_input.to_record(),
            "output": self.output.to_record(),
        }


def build_deterministic_decision(
    snapshot: StrategySnapshot,
    *,
    config: DeterministicProposalConfig,
) -> DeterministicDecisionResult:
    """Build a canonical proposal or no-trade decision from a strategy snapshot."""

    serialized_snapshot = serialize_strategy_snapshot(snapshot)
    decision_id = _stable_id("decision", serialized_snapshot)
    run_id = snapshot.metadata.get("run_id", "unknown-run")
    market_snapshot = _market_snapshot_from_strategy_snapshot(snapshot)
    decision_input = DecisionInput(
        decision_id=decision_id,
        run_id=run_id,
        mode=config.mode,
        market=market_snapshot,
        config_hash=snapshot.config_hash,
        created_at_ms=snapshot.timestamp_ms,
        allowed_symbols=config.allowed_symbols,
        source=SignalSource.DETERMINISTIC,
        strategy_snapshot=serialized_snapshot,
        max_market_age_ms=config.max_market_age_ms,
        metadata={"strategy_snapshot_schema": SNAPSHOT_SCHEMA_VERSION},
    )

    if snapshot.symbol not in config.allowed_symbols:
        return DeterministicDecisionResult(
            decision_input=decision_input,
            output=_no_trade(
                decision_input,
                reason=NoTradeReason.OUT_OF_UNIVERSE,
                rationale=f"{snapshot.symbol} is not in the allowed decision universe",
                confidence=snapshot.entry.strength,
            ),
        )

    missing_reason = _entry_missing_reason(snapshot)
    if missing_reason is not None:
        return DeterministicDecisionResult(
            decision_input=decision_input,
            output=_no_trade(
                decision_input,
                reason=NoTradeReason.NO_SIGNAL,
                rationale=missing_reason,
                confidence=snapshot.entry.strength,
            ),
        )

    assert snapshot.entry.side is not None
    assert snapshot.sizing_input is not None
    assert snapshot.position_size is not None
    assert snapshot.stop_plan is not None

    proposal = TradeProposal(
        proposal_id=_stable_id("proposal", serialized_snapshot),
        decision_id=decision_id,
        run_id=run_id,
        mode=config.mode,
        source=SignalSource.DETERMINISTIC,
        symbol=snapshot.symbol,
        action=ProposalAction.ENTER,
        side=snapshot.entry.side,
        order_type=config.order_type,
        quantity=snapshot.position_size.quantity,
        notional=snapshot.position_size.notional,
        entry_price=snapshot.sizing_input.entry_price,
        stop_loss_price=snapshot.stop_plan.stop_price,
        take_profit_price=snapshot.stop_plan.take_profit_price,
        confidence=snapshot.entry.strength,
        rationale=snapshot.entry.reason,
        created_at_ms=snapshot.timestamp_ms,
        valid_until_ms=snapshot.timestamp_ms + config.proposal_ttl_ms,
        risk_tags=("requires_supervisor_review", "deterministic_snapshot"),
        metadata={
            "config_hash": snapshot.config_hash,
            "strategy_snapshot_schema": SNAPSHOT_SCHEMA_VERSION,
            "regime": snapshot.regime.label.value,
        },
    )
    return DeterministicDecisionResult(decision_input=decision_input, output=proposal)


def _entry_missing_reason(snapshot: StrategySnapshot) -> Optional[str]:
    if snapshot.entry.action is not EntryDecision.ENTER:
        return snapshot.entry.reason
    if snapshot.entry.side is None:
        return "entry side is missing"
    if snapshot.sizing_input is None:
        return "sizing input is missing"
    if snapshot.position_size is None:
        return "position size is missing"
    if snapshot.stop_plan is None:
        return "stop plan is missing"
    if snapshot.position_size.quantity <= Decimal("0") or snapshot.position_size.notional <= Decimal("0"):
        return "position size is zero"
    return None


def _market_snapshot_from_strategy_snapshot(snapshot: StrategySnapshot) -> MarketSnapshot:
    latest_close = snapshot.metadata.get("latest_close")
    if latest_close is None and snapshot.sizing_input is not None:
        latest_close = str(snapshot.sizing_input.entry_price)
    if latest_close is None:
        raise ValueError("strategy snapshot metadata must include latest_close for decisioning")

    return MarketSnapshot(
        snapshot_id=_stable_id("market", serialize_strategy_snapshot(snapshot)),
        symbol=snapshot.symbol,
        timeframe=snapshot.timeframe,
        timestamp_ms=snapshot.timestamp_ms,
        mark_price=Decimal(latest_close),
        source="strategy_snapshot",
        features={
            "regime": snapshot.regime.label.value,
            "entry_action": snapshot.entry.action.value,
            "exit_action": snapshot.exit.action.value,
        },
    )


def _no_trade(
    decision_input: DecisionInput,
    *,
    reason: NoTradeReason,
    rationale: str,
    confidence: Decimal,
) -> NoTradeDecision:
    return NoTradeDecision(
        decision_id=decision_input.decision_id,
        run_id=decision_input.run_id,
        mode=decision_input.mode,
        source=SignalSource.DETERMINISTIC,
        symbol=decision_input.market.symbol,
        reason=reason,
        rationale=rationale,
        confidence=confidence,
        created_at_ms=decision_input.created_at_ms,
        metadata={"config_hash": decision_input.config_hash},
    )


def _stable_id(prefix: str, payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()[:16]}"


__all__ = [
    "DeterministicDecisionResult",
    "DeterministicProposalConfig",
    "build_deterministic_decision",
]
