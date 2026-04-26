from __future__ import annotations

from decimal import Decimal

import pytest

from apps.supervisor.health import HealthStatus, build_supervisor_health
from apps.supervisor.main import main as supervisor_main
from apps.supervisor.service import SupervisorConfig, SupervisorService
from libs.decisioning.schemas import DecisionMode, OrderIntentType, ProposalAction, SignalSource, TradeProposal
from libs.risk import AccountRiskLimits, AccountRiskState, DrawdownLimits, DrawdownState, PositionLimitConfig
from libs.strategy.interfaces import TradeSide


def test_supervisor_allows_policy_approved_paper_proposal() -> None:
    evaluation = SupervisorService(SupervisorConfig(_limits())).evaluate_proposal(_proposal(), _state())

    assert evaluation.accepted is True
    assert evaluation.risk_decision.allowed is True
    assert evaluation.health.status is HealthStatus.OK
    record = evaluation.to_record()
    assert record["schema_version"] == "supervisor_policy_evaluation.v1"
    assert record["risk_decision"]["primary_reason"] == "allowed"
    assert record["health"]["status"] == "ok"


def test_supervisor_vetoes_proposal_and_reports_degraded_health() -> None:
    evaluation = SupervisorService(SupervisorConfig(_limits())).evaluate_proposal(
        _proposal(notional=Decimal("2500")),
        _state(entries_frozen=True),
    )

    assert evaluation.accepted is False
    assert evaluation.risk_decision.allowed is False
    assert evaluation.risk_decision.primary_reason == "entries_frozen"
    assert evaluation.health.status is HealthStatus.DEGRADED
    assert [check.name for check in evaluation.health.checks if check.status is HealthStatus.DEGRADED] == ["entries"]


def test_supervisor_health_stops_when_kill_switch_is_active() -> None:
    health = SupervisorService(SupervisorConfig(_limits())).health(_state(kill_switch_active=True))

    assert health.status is HealthStatus.STOPPED
    assert health.to_record()["checks"][-1]["name"] == "kill_switch"
    assert health.to_record()["checks"][-1]["status"] == "stopped"


def test_supervisor_health_degrades_on_drawdown_limit_breach() -> None:
    health = build_supervisor_health(
        state=_state(current_equity=Decimal("8500"), peak_equity=Decimal("10000"), day_start_equity=Decimal("9000")),
        limits=_limits(max_peak_drawdown=Decimal("0.10"), max_daily_drawdown=Decimal("0.05")),
    )

    assert health.status is HealthStatus.DEGRADED
    drawdown_check = next(check for check in health.checks if check.name == "drawdown")
    assert drawdown_check.status is HealthStatus.DEGRADED
    assert drawdown_check.details["reason"] == "peak_drawdown_exceeded"


def test_supervisor_rejects_disabled_risk_governor() -> None:
    with pytest.raises(ValueError, match="risk governor"):
        SupervisorConfig(_limits(), risk_enabled=False)


def test_supervisor_entrypoint_boots_with_local_config() -> None:
    assert supervisor_main() == 0


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
    entries_frozen: bool = False,
    kill_switch_active: bool = False,
) -> AccountRiskState:
    return AccountRiskState(
        drawdown=DrawdownState(
            current_equity=current_equity,
            peak_equity=peak_equity,
            day_start_equity=day_start_equity,
        ),
        entries_frozen=entries_frozen,
        kill_switch_active=kill_switch_active,
    )


def _proposal(
    *,
    action: ProposalAction = ProposalAction.ENTER,
    notional: Decimal = Decimal("500"),
    mode: DecisionMode = DecisionMode.PAPER,
) -> TradeProposal:
    return TradeProposal(
        proposal_id="proposal-1",
        decision_id="decision-1",
        run_id="run-1",
        mode=mode,
        source=SignalSource.DETERMINISTIC,
        symbol="BTC/USDT",
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
