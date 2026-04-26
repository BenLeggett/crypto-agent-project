from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from apps.decision_engine.validators import (
    DecisionValidationError,
    rejection_reason_for_error,
    validate_decision_input,
    validate_no_trade_decision,
    validate_trade_proposal,
)
from libs.decisioning.schemas import (
    DECISION_INPUT_SCHEMA_VERSION,
    MARKET_SNAPSHOT_SCHEMA_VERSION,
    NO_TRADE_SCHEMA_VERSION,
    REJECTION_SCHEMA_VERSION,
    TRADE_PROPOSAL_SCHEMA_VERSION,
    DecisionInput,
    DecisionMode,
    DecisionSchemaError,
    MarketSnapshot,
    NoTradeDecision,
    NoTradeReason,
    OrderIntentType,
    ProposalAction,
    ProposalRejection,
    ProposalRejectionReason,
    SignalSource,
    TradeProposal,
    decimal_from_record,
)
from libs.strategy.interfaces import TradeSide


def _market_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        snapshot_id="snapshot-1",
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp_ms=1_700_000_000_000,
        mark_price=Decimal("42000.50"),
        bid_price=Decimal("42000.00"),
        ask_price=Decimal("42001.00"),
        source="fixture",
        features={"regime": "bull"},
    )


def _decision_input() -> DecisionInput:
    return DecisionInput(
        decision_id="decision-1",
        run_id="run-1",
        mode=DecisionMode.PAPER,
        market=_market_snapshot(),
        config_hash="config-hash",
        created_at_ms=1_700_000_010_000,
        allowed_symbols=("BTC/USDT", "ETH/USDT"),
        source=SignalSource.DETERMINISTIC,
        strategy_snapshot={"schema_version": "strategy_snapshot.v1"},
    )


def _trade_proposal() -> TradeProposal:
    return TradeProposal(
        proposal_id="proposal-1",
        decision_id="decision-1",
        run_id="run-1",
        mode=DecisionMode.PAPER,
        source=SignalSource.DETERMINISTIC,
        symbol="BTC/USDT",
        action=ProposalAction.ENTER,
        side=TradeSide.LONG,
        order_type=OrderIntentType.LIMIT,
        quantity=Decimal("0.01"),
        notional=Decimal("420.00"),
        entry_price=Decimal("42000"),
        stop_loss_price=Decimal("39900"),
        take_profit_price=Decimal("46200"),
        confidence=Decimal("0.72"),
        rationale="breakout snapshot met deterministic criteria",
        created_at_ms=1_700_000_010_000,
        valid_until_ms=1_700_000_070_000,
        risk_tags=("requires_supervisor_review",),
    )


def test_market_snapshot_is_versioned_serializable_and_immutable() -> None:
    snapshot = _market_snapshot()

    record = snapshot.to_record()
    assert record["schema_version"] == MARKET_SNAPSHOT_SCHEMA_VERSION
    assert record["mark_price"] == "42000.5"
    assert record["bid_price"] == "42000"
    assert record["features"] == {"regime": "bull"}
    with pytest.raises(FrozenInstanceError):
        snapshot.symbol = "ETH/USDT"  # type: ignore[misc]


def test_decision_input_schema_validates_allowed_market_and_staleness() -> None:
    decision_input = _decision_input()

    record = validate_decision_input(decision_input).to_record()
    assert record["schema_version"] == DECISION_INPUT_SCHEMA_VERSION
    assert record["mode"] == "paper"
    assert record["market"]["symbol"] == "BTC/USDT"
    assert record["allowed_symbols"] == ["BTC/USDT", "ETH/USDT"]

    stale_input = DecisionInput(
        decision_id="decision-2",
        run_id="run-1",
        mode=DecisionMode.PAPER,
        market=_market_snapshot(),
        config_hash="config-hash",
        created_at_ms=1_700_001_000_001,
        allowed_symbols=("BTC/USDT",),
        source=SignalSource.DETERMINISTIC,
    )
    with pytest.raises(DecisionValidationError, match="stale"):
        validate_decision_input(stale_input)


def test_trade_proposal_is_structured_serializable_and_context_validated() -> None:
    proposal = _trade_proposal()

    record = validate_trade_proposal(proposal, decision_input=_decision_input(), now_ms=1_700_000_020_000).to_record()
    assert record["schema_version"] == TRADE_PROPOSAL_SCHEMA_VERSION
    assert record["action"] == "enter"
    assert record["side"] == "long"
    assert record["quantity"] == "0.01"
    assert record["risk_tags"] == ["requires_supervisor_review"]
    assert "exchange" not in record
    assert "api_key" not in record
    assert not hasattr(proposal, "place_order")


def test_trade_proposal_rejects_malformed_or_unsafe_shape() -> None:
    with pytest.raises(DecisionSchemaError, match="rationale"):
        TradeProposal(
            proposal_id="proposal-1",
            decision_id="decision-1",
            run_id="run-1",
            mode=DecisionMode.PAPER,
            source=SignalSource.DETERMINISTIC,
            symbol="BTC/USDT",
            action=ProposalAction.ENTER,
            side=TradeSide.LONG,
            order_type=OrderIntentType.LIMIT,
            quantity=Decimal("0.01"),
            notional=Decimal("420.00"),
            entry_price=Decimal("42000"),
            stop_loss_price=Decimal("39900"),
            confidence=Decimal("0.72"),
            rationale="",
            created_at_ms=1_700_000_010_000,
            valid_until_ms=1_700_000_070_000,
        )
    with pytest.raises(DecisionSchemaError, match="long stop_loss_price"):
        TradeProposal(
            proposal_id="proposal-2",
            decision_id="decision-1",
            run_id="run-1",
            mode=DecisionMode.PAPER,
            source=SignalSource.DETERMINISTIC,
            symbol="BTC/USDT",
            action=ProposalAction.ENTER,
            side=TradeSide.LONG,
            order_type=OrderIntentType.LIMIT,
            quantity=Decimal("0.01"),
            notional=Decimal("420.00"),
            entry_price=Decimal("42000"),
            stop_loss_price=Decimal("42100"),
            confidence=Decimal("0.72"),
            rationale="bad stop",
            created_at_ms=1_700_000_010_000,
            valid_until_ms=1_700_000_070_000,
        )


def test_trade_proposal_fails_closed_for_out_of_context_symbol_and_future_live() -> None:
    proposal = _trade_proposal()
    wrong_context = DecisionInput(
        decision_id="decision-1",
        run_id="run-1",
        mode=DecisionMode.PAPER,
        market=MarketSnapshot(
            snapshot_id="snapshot-2",
            symbol="ETH/USDT",
            timeframe="4h",
            timestamp_ms=1_700_000_000_000,
            mark_price=Decimal("2200"),
            source="fixture",
        ),
        config_hash="config-hash",
        created_at_ms=1_700_000_010_000,
        allowed_symbols=("ETH/USDT",),
        source=SignalSource.DETERMINISTIC,
    )
    with pytest.raises(DecisionValidationError, match="symbol"):
        validate_trade_proposal(proposal, decision_input=wrong_context)

    future_live = TradeProposal(
        proposal_id="proposal-live",
        decision_id="decision-1",
        run_id="run-1",
        mode=DecisionMode.FUTURE_LIVE,
        source=SignalSource.DETERMINISTIC,
        symbol="BTC/USDT",
        action=ProposalAction.ENTER,
        side=TradeSide.LONG,
        order_type=OrderIntentType.LIMIT,
        quantity=Decimal("0.01"),
        notional=Decimal("420.00"),
        entry_price=Decimal("42000"),
        stop_loss_price=Decimal("39900"),
        confidence=Decimal("0.72"),
        rationale="future live is gated",
        created_at_ms=1_700_000_010_000,
        valid_until_ms=1_700_000_070_000,
    )
    with pytest.raises(DecisionValidationError, match="future live"):
        validate_trade_proposal(future_live)


def test_no_trade_and_rejection_records_are_versioned() -> None:
    no_trade = NoTradeDecision(
        decision_id="decision-1",
        run_id="run-1",
        mode=DecisionMode.PAPER,
        source=SignalSource.MODEL_INFORMED,
        symbol="BTC/USDT",
        reason=NoTradeReason.NO_SIGNAL,
        rationale="model-informed job emitted no-trade",
        confidence=Decimal("0.61"),
        created_at_ms=1_700_000_010_000,
    )
    rejection = ProposalRejection(
        rejection_id="reject-1",
        decision_id="decision-1",
        proposal_id="proposal-1",
        reason=ProposalRejectionReason.SIZE_INVALID,
        message="quantity exceeds schema bounds",
        created_at_ms=1_700_000_011_000,
    )

    assert validate_no_trade_decision(no_trade, decision_input=_decision_input()).to_record()["schema_version"] == NO_TRADE_SCHEMA_VERSION
    assert rejection.to_record()["schema_version"] == REJECTION_SCHEMA_VERSION
    assert rejection_reason_for_error(DecisionValidationError("proposal is expired")) is ProposalRejectionReason.STALE_DATA


def test_decimal_from_record_rejects_bad_values() -> None:
    assert decimal_from_record("1.25", "field") == Decimal("1.25")
    with pytest.raises(DecisionSchemaError, match="decimal"):
        decimal_from_record("not-a-number", "field")
