from __future__ import annotations

from decimal import Decimal
from typing import Optional

import pytest

from apps.decision_engine.validators import (
    DecisionValidationError,
    build_trade_proposal_validation_report,
    validate_trade_proposal,
)
from libs.decisioning.scoring import ProposalValidationPolicy
from libs.decisioning.schemas import (
    DecisionInput,
    DecisionMode,
    MarketSnapshot,
    OrderIntentType,
    ProposalAction,
    ProposalRejectionReason,
    SignalSource,
    TradeProposal,
)
from libs.strategy.interfaces import TradeSide


def _market_snapshot(*, symbol: str = "BTC/USDT", timestamp_ms: int = 1_700_000_000_000) -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id="snapshot-1",
        symbol=symbol,
        timeframe="4h",
        timestamp_ms=timestamp_ms,
        mark_price=Decimal("42000"),
        source="fixture",
    )


def _decision_input(
    *,
    market: Optional[MarketSnapshot] = None,
    allowed_symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT"),
    created_at_ms: int = 1_700_000_010_000,
    max_market_age_ms: int = 300_000,
) -> DecisionInput:
    return DecisionInput(
        decision_id="decision-1",
        run_id="run-1",
        mode=DecisionMode.PAPER,
        market=market or _market_snapshot(),
        config_hash="config-hash",
        created_at_ms=created_at_ms,
        allowed_symbols=allowed_symbols,
        source=SignalSource.DETERMINISTIC,
        max_market_age_ms=max_market_age_ms,
    )


def _proposal(**overrides: object) -> TradeProposal:
    values = {
        "proposal_id": "proposal-1",
        "decision_id": "decision-1",
        "run_id": "run-1",
        "mode": DecisionMode.PAPER,
        "source": SignalSource.DETERMINISTIC,
        "symbol": "BTC/USDT",
        "action": ProposalAction.ENTER,
        "side": TradeSide.LONG,
        "order_type": OrderIntentType.LIMIT,
        "quantity": Decimal("0.01"),
        "notional": Decimal("420"),
        "entry_price": Decimal("42000"),
        "stop_loss_price": Decimal("39900"),
        "confidence": Decimal("0.70"),
        "rationale": "deterministic breakout criteria passed",
        "created_at_ms": 1_700_000_010_000,
        "valid_until_ms": 1_700_000_070_000,
    }
    values.update(overrides)
    return TradeProposal(**values)


def _policy(**overrides: object) -> ProposalValidationPolicy:
    values = {
        "allowed_symbols": ("BTC/USDT", "ETH/USDT"),
        "max_notional": Decimal("1000"),
        "max_quantity": Decimal("1"),
    }
    values.update(overrides)
    return ProposalValidationPolicy(**values)


def test_validation_report_passes_for_fresh_in_universe_proposal() -> None:
    report = build_trade_proposal_validation_report(
        _proposal(),
        decision_input=_decision_input(),
        policy=_policy(),
        now_ms=1_700_000_020_000,
    )

    assert report.passed is True
    assert report.issues == ()
    assert validate_trade_proposal(
        _proposal(),
        decision_input=_decision_input(),
        policy=_policy(),
        now_ms=1_700_000_020_000,
    ).proposal_id == "proposal-1"


def test_validation_report_fails_closed_for_stale_market_snapshot() -> None:
    stale_input = _decision_input(
        market=_market_snapshot(timestamp_ms=1_700_000_000_000),
        created_at_ms=1_700_001_000_000,
        max_market_age_ms=300_000,
    )

    report = build_trade_proposal_validation_report(_proposal(), decision_input=stale_input, policy=_policy())

    assert report.passed is False
    assert report.issues[0].reason is ProposalRejectionReason.STALE_DATA
    assert report.issues[0].field == "market.timestamp_ms"
    with pytest.raises(DecisionValidationError, match="market snapshot is stale"):
        validate_trade_proposal(_proposal(), decision_input=stale_input, policy=_policy())


def test_validation_report_fails_closed_for_expired_proposal() -> None:
    report = build_trade_proposal_validation_report(
        _proposal(),
        decision_input=_decision_input(),
        policy=_policy(),
        now_ms=1_700_000_080_000,
    )

    assert report.passed is False
    assert report.issues[0].reason is ProposalRejectionReason.STALE_DATA
    assert report.issues[0].field == "valid_until_ms"


def test_validation_report_fails_closed_for_out_of_universe_symbol() -> None:
    report = build_trade_proposal_validation_report(
        _proposal(symbol="SOL/USDT"),
        decision_input=_decision_input(),
        policy=_policy(allowed_symbols=("BTC/USDT",)),
    )

    reasons = [issue.reason for issue in report.issues]
    assert report.passed is False
    assert ProposalRejectionReason.SYMBOL_NOT_ALLOWED in reasons


def test_validation_report_fails_closed_for_oversized_proposal() -> None:
    report = build_trade_proposal_validation_report(
        _proposal(quantity=Decimal("2"), notional=Decimal("2000")),
        decision_input=_decision_input(),
        policy=_policy(max_notional=Decimal("1000"), max_quantity=Decimal("1")),
    )

    assert report.passed is False
    assert [issue.field for issue in report.issues if issue.reason is ProposalRejectionReason.SIZE_INVALID] == [
        "notional",
        "quantity",
    ]


def test_validation_report_converts_issues_to_structured_rejections() -> None:
    report = build_trade_proposal_validation_report(
        _proposal(notional=Decimal("2000")),
        decision_input=_decision_input(),
        policy=_policy(max_notional=Decimal("1000")),
    )

    rejections = report.to_rejections(created_at_ms=1_700_000_020_000)

    assert len(rejections) == 1
    assert rejections[0].decision_id == "decision-1"
    assert rejections[0].proposal_id == "proposal-1"
    assert rejections[0].reason is ProposalRejectionReason.SIZE_INVALID
    assert rejections[0].metadata["field"] == "notional"
