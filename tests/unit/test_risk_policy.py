from __future__ import annotations

from decimal import Decimal

import pytest

from libs.decisioning.schemas import DecisionMode, OrderIntentType, ProposalAction, SignalSource, TradeProposal
from libs.risk import (
    AccountRiskLimits,
    AccountRiskPolicy,
    AccountRiskState,
    DrawdownLimits,
    DrawdownState,
    OpenPosition,
    PositionLimitConfig,
    calculate_drawdown,
    evaluate_account_policy,
    evaluate_drawdown,
    evaluate_position_limits,
)
from libs.strategy.interfaces import TradeSide


def test_account_policy_allows_entry_inside_hard_limits() -> None:
    decision = evaluate_account_policy(
        _proposal(),
        limits=_limits(),
        state=_state(),
    )

    assert decision.allowed is True
    assert decision.primary_reason == "allowed"
    record = decision.to_record()
    assert record["schema_version"] == "risk_policy_decision.v1"
    assert record["issues"] == []


def test_account_policy_vetoes_frozen_entries_but_allows_exits() -> None:
    frozen_state = _state(entries_frozen=True)

    entry_decision = evaluate_account_policy(_proposal(), limits=_limits(), state=frozen_state)
    exit_decision = evaluate_account_policy(
        _proposal(action=ProposalAction.EXIT),
        limits=_limits(),
        state=frozen_state,
    )

    assert entry_decision.allowed is False
    assert entry_decision.primary_reason == "entries_frozen"
    assert exit_decision.allowed is True


def test_account_policy_vetoes_out_of_universe_and_future_live_proposals() -> None:
    wrong_symbol = evaluate_account_policy(
        _proposal(symbol="SOL/USDT"),
        limits=_limits(allowed_symbols=("BTC/USDT",)),
        state=_state(),
    )
    future_live = evaluate_account_policy(
        _proposal(mode=DecisionMode.FUTURE_LIVE),
        limits=_limits(),
        state=_state(),
    )

    assert wrong_symbol.allowed is False
    assert wrong_symbol.primary_reason == "symbol_not_allowed"
    assert future_live.allowed is False
    assert future_live.primary_reason == "mode_not_allowed"


def test_account_policy_vetoes_drawdown_and_kill_switch() -> None:
    drawdown_decision = evaluate_account_policy(
        _proposal(),
        limits=_limits(max_peak_drawdown=Decimal("0.10"), max_daily_drawdown=Decimal("0.05")),
        state=_state(current_equity=Decimal("8500"), peak_equity=Decimal("10000"), day_start_equity=Decimal("9000")),
    )
    kill_switch_decision = evaluate_account_policy(
        _proposal(),
        limits=_limits(),
        state=_state(kill_switch_active=True),
    )

    assert drawdown_decision.allowed is False
    assert drawdown_decision.primary_reason == "peak_drawdown_exceeded"
    assert kill_switch_decision.allowed is False
    assert kill_switch_decision.primary_reason == "kill_switch_active"


def test_account_policy_vetoes_position_exposure_limits() -> None:
    decision = evaluate_account_policy(
        _proposal(notional=Decimal("700")),
        limits=_limits(max_order_notional=Decimal("1000"), max_symbol_exposure=Decimal("1000")),
        state=_state(open_positions=(OpenPosition("BTC/USDT", TradeSide.LONG, Decimal("400")),)),
    )

    assert decision.allowed is False
    assert decision.primary_reason == "max_symbol_exposure_exceeded"


def test_drawdown_and_position_helpers_are_deterministic() -> None:
    drawdown = evaluate_drawdown(
        DrawdownState(
            current_equity=Decimal("9500"),
            peak_equity=Decimal("10000"),
            day_start_equity=Decimal("9800"),
        ),
        DrawdownLimits(max_peak_drawdown=Decimal("0.10"), max_daily_drawdown=Decimal("0.05")),
    )
    position = evaluate_position_limits(
        symbol="BTC/USDT",
        proposal_notional=Decimal("250"),
        open_positions=(OpenPosition("BTC/USDT", TradeSide.LONG, Decimal("500")),),
        limits=PositionLimitConfig(
            max_order_notional=Decimal("1000"),
            max_symbol_exposure=Decimal("1000"),
            max_total_exposure=Decimal("2000"),
        ),
    )

    assert calculate_drawdown(Decimal("9500"), Decimal("10000")) == Decimal("0.05")
    assert drawdown.passed is True
    assert drawdown.to_record()["reason"] == "drawdown_within_limits"
    assert position.passed is True
    assert position.to_record()["projected_symbol_exposure"] == "750"


def test_account_policy_requires_structured_trade_proposal() -> None:
    with pytest.raises(TypeError, match="TradeProposal"):
        AccountRiskPolicy(_limits()).evaluate(object(), _state())  # type: ignore[arg-type]


def _limits(
    *,
    allowed_symbols: tuple[str, ...] = ("BTC/USDT", "ETH/USDT"),
    max_order_notional: Decimal = Decimal("1000"),
    max_symbol_exposure: Decimal = Decimal("1500"),
    max_total_exposure: Decimal = Decimal("3000"),
    max_peak_drawdown: Decimal = Decimal("0.20"),
    max_daily_drawdown: Decimal = Decimal("0.10"),
) -> AccountRiskLimits:
    return AccountRiskLimits(
        allowed_symbols=allowed_symbols,
        position_limits=PositionLimitConfig(
            max_order_notional=max_order_notional,
            max_symbol_exposure=max_symbol_exposure,
            max_total_exposure=max_total_exposure,
        ),
        drawdown_limits=DrawdownLimits(
            max_peak_drawdown=max_peak_drawdown,
            max_daily_drawdown=max_daily_drawdown,
        ),
    )


def _state(
    *,
    current_equity: Decimal = Decimal("10000"),
    peak_equity: Decimal = Decimal("10000"),
    day_start_equity: Decimal = Decimal("10000"),
    open_positions: tuple[OpenPosition, ...] = (),
    entries_frozen: bool = False,
    kill_switch_active: bool = False,
) -> AccountRiskState:
    return AccountRiskState(
        drawdown=DrawdownState(
            current_equity=current_equity,
            peak_equity=peak_equity,
            day_start_equity=day_start_equity,
        ),
        open_positions=open_positions,
        entries_frozen=entries_frozen,
        kill_switch_active=kill_switch_active,
    )


def _proposal(
    *,
    symbol: str = "BTC/USDT",
    mode: DecisionMode = DecisionMode.PAPER,
    action: ProposalAction = ProposalAction.ENTER,
    notional: Decimal = Decimal("500"),
) -> TradeProposal:
    return TradeProposal(
        proposal_id="proposal-1",
        decision_id="decision-1",
        run_id="run-1",
        mode=mode,
        source=SignalSource.DETERMINISTIC,
        symbol=symbol,
        action=action,
        side=TradeSide.LONG,
        order_type=OrderIntentType.LIMIT,
        quantity=Decimal("0.01"),
        notional=notional,
        entry_price=Decimal("50000"),
        stop_loss_price=Decimal("47500"),
        confidence=Decimal("0.75"),
        rationale="deterministic breakout criteria passed",
        created_at_ms=1_700_000_000_000,
        valid_until_ms=1_700_000_060_000,
    )
