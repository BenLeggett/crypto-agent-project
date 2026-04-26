from __future__ import annotations

from decimal import Decimal

from apps.decision_engine.proposal_builder import DeterministicProposalBuilder
from apps.decision_engine.validators import validate_no_trade_decision, validate_trade_proposal
from libs.decisioning.deterministic_rules import DeterministicProposalConfig, build_deterministic_decision
from libs.decisioning.schemas import DecisionMode, NoTradeDecision, NoTradeReason, TradeProposal
from libs.strategy.interfaces import (
    EntryDecision,
    EntrySignal,
    ExitDecision,
    ExitSignal,
    PositionSize,
    RegimeAssessment,
    RegimeLabel,
    SizingInput,
    StopPlan,
    StrategySnapshot,
    TradeSide,
)


def _entry_snapshot() -> StrategySnapshot:
    return StrategySnapshot(
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp_ms=1_700_000_000_000,
        config_hash="config-sha",
        regime=RegimeAssessment(
            label=RegimeLabel.BULL,
            confidence=Decimal("0.8"),
            as_of_ms=1_700_000_000_000,
            reason="bull regime",
        ),
        entry=EntrySignal(
            symbol="BTC/USDT",
            timeframe="4h",
            action=EntryDecision.ENTER,
            side=TradeSide.LONG,
            strength=Decimal("0.75"),
            timestamp_ms=1_700_000_000_000,
            reason="breakout above prior range",
        ),
        exit=ExitSignal(
            symbol="BTC/USDT",
            timeframe="4h",
            action=ExitDecision.HOLD,
            side=None,
            strength=Decimal("0"),
            timestamp_ms=1_700_000_000_000,
            reason="no exit",
        ),
        sizing_input=SizingInput(
            symbol="BTC/USDT",
            side=TradeSide.LONG,
            equity=Decimal("10000"),
            risk_fraction=Decimal("0.01"),
            entry_price=Decimal("105"),
            stop_price=Decimal("100"),
            max_position_value=Decimal("5000"),
        ),
        position_size=PositionSize(
            symbol="BTC/USDT",
            side=TradeSide.LONG,
            quantity=Decimal("2.5"),
            notional=Decimal("262.5"),
            risk_amount=Decimal("12.5"),
            reason="risk-budget size",
        ),
        stop_plan=StopPlan(
            symbol="BTC/USDT",
            side=TradeSide.LONG,
            stop_price=Decimal("100"),
            take_profit_price=Decimal("115"),
            trailing_distance=None,
            reason="range stop",
        ),
        metadata={
            "run_id": "run-1",
            "schema_version": "strategy_snapshot.v1",
            "latest_close": "105",
        },
    )


def _hold_snapshot() -> StrategySnapshot:
    base = _entry_snapshot()
    return StrategySnapshot(
        symbol=base.symbol,
        timeframe=base.timeframe,
        timestamp_ms=base.timestamp_ms,
        config_hash=base.config_hash,
        regime=base.regime,
        entry=EntrySignal(
            symbol=base.symbol,
            timeframe=base.timeframe,
            action=EntryDecision.HOLD,
            side=None,
            strength=Decimal("0.25"),
            timestamp_ms=base.timestamp_ms,
            reason="breakout criteria not met",
        ),
        exit=base.exit,
        sizing_input=None,
        position_size=None,
        stop_plan=None,
        metadata=dict(base.metadata),
    )


def test_deterministic_builder_emits_stable_trade_proposal_from_entry_snapshot() -> None:
    config = DeterministicProposalConfig(allowed_symbols=("BTC/USDT",), proposal_ttl_ms=60_000)
    first = build_deterministic_decision(_entry_snapshot(), config=config)
    second = build_deterministic_decision(_entry_snapshot(), config=config)

    assert isinstance(first.output, TradeProposal)
    assert first.to_record() == second.to_record()
    assert first.decision_input.market.mark_price == Decimal("105")
    assert first.output.symbol == "BTC/USDT"
    assert first.output.quantity == Decimal("2.5")
    assert first.output.notional == Decimal("262.5")
    assert first.output.entry_price == Decimal("105")
    assert first.output.stop_loss_price == Decimal("100")
    assert first.output.valid_until_ms == 1_700_000_060_000
    assert "requires_supervisor_review" in first.output.risk_tags
    assert validate_trade_proposal(first.output, decision_input=first.decision_input) is first.output
    assert not hasattr(first.output, "place_order")


def test_app_proposal_builder_delegates_to_deterministic_rules() -> None:
    builder = DeterministicProposalBuilder(
        DeterministicProposalConfig(allowed_symbols=("BTC/USDT",), mode=DecisionMode.PAPER)
    )

    result = builder.build(_entry_snapshot())

    assert isinstance(result.output, TradeProposal)
    assert result.output.mode is DecisionMode.PAPER


def test_deterministic_builder_emits_no_trade_when_snapshot_has_no_entry() -> None:
    result = build_deterministic_decision(
        _hold_snapshot(),
        config=DeterministicProposalConfig(allowed_symbols=("BTC/USDT",)),
    )

    assert isinstance(result.output, NoTradeDecision)
    assert result.output.reason is NoTradeReason.NO_SIGNAL
    assert result.output.rationale == "breakout criteria not met"
    assert validate_no_trade_decision(result.output, decision_input=result.decision_input) is result.output


def test_deterministic_builder_emits_no_trade_for_out_of_universe_symbol() -> None:
    result = build_deterministic_decision(
        _entry_snapshot(),
        config=DeterministicProposalConfig(allowed_symbols=("ETH/USDT",)),
    )

    assert isinstance(result.output, NoTradeDecision)
    assert result.output.reason is NoTradeReason.OUT_OF_UNIVERSE
    assert "not in the allowed" in result.output.rationale
