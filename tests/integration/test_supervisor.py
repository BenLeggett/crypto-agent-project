from __future__ import annotations

from decimal import Decimal

from apps.supervisor.health import HealthStatus
from apps.supervisor.kill_switch import activate_kill_switch, build_flatten_workflow_request
from apps.supervisor.reconciliation import (
    AccountSnapshot,
    BalanceSnapshot,
    PositionSnapshot,
    ReconciliationStatus,
    reconcile_account_snapshots,
)
from apps.supervisor.service import SupervisorConfig, SupervisorService
from libs.decisioning.schemas import DecisionMode, OrderIntentType, ProposalAction, SignalSource, TradeProposal
from libs.risk import (
    AccountRiskLimits,
    AccountRiskState,
    DrawdownLimits,
    DrawdownState,
    FreezeState,
    PositionLimitConfig,
    SupervisorControlAction,
    SupervisorControlCommand,
    apply_control_command,
)
from libs.strategy.interfaces import TradeSide


def test_supervisor_policy_freeze_and_degraded_health_work_together() -> None:
    service = SupervisorService(SupervisorConfig(_limits()))
    proposal = _proposal()
    healthy_state = _state()

    approved = service.evaluate_proposal(proposal, healthy_state)
    frozen = apply_control_command(FreezeState(), _command(SupervisorControlAction.FREEZE_ENTRIES))
    frozen_evaluation = service.evaluate_proposal_with_controls(proposal, healthy_state, frozen)
    drawdown_evaluation = service.evaluate_proposal(
        proposal,
        _state(current_equity=Decimal("8500"), peak_equity=Decimal("10000"), day_start_equity=Decimal("9000")),
    )

    assert approved.accepted is True
    assert approved.health.status is HealthStatus.OK
    assert frozen_evaluation.accepted is False
    assert frozen_evaluation.risk_decision.primary_reason == "entries_frozen"
    assert frozen_evaluation.health.status is HealthStatus.DEGRADED
    assert drawdown_evaluation.accepted is False
    assert drawdown_evaluation.risk_decision.primary_reason == "peak_drawdown_exceeded"
    assert drawdown_evaluation.health.status is HealthStatus.DEGRADED


def test_supervisor_kill_switch_triggers_stopped_health_and_non_executing_flatten_request() -> None:
    service = SupervisorService(SupervisorConfig(_limits()))
    killed = activate_kill_switch(
        command_id="kill-1",
        run_id="run-1",
        reason="paper safety drill",
        actor="operator",
        created_at_ms=1_700_000_000_000,
    )
    flatten = build_flatten_workflow_request(
        request_id="flatten-1",
        run_id="run-1",
        reason="paper safety drill",
        actor="operator",
        created_at_ms=1_700_000_000_001,
        state=killed,
    )
    evaluation = service.evaluate_proposal_with_controls(_proposal(), _state(), killed)

    assert killed.kill_switch_active is True
    assert killed.entries_frozen is True
    assert killed.flatten_requested is True
    assert flatten.execution_enabled is False
    assert flatten.state.flatten_requested is True
    assert evaluation.accepted is False
    assert evaluation.risk_decision.primary_reason == "kill_switch_active"
    assert evaluation.health.status is HealthStatus.STOPPED


def test_supervisor_reconciliation_mismatch_is_classified_for_operator_review() -> None:
    internal = AccountSnapshot(
        snapshot_id="internal-1",
        source="internal_state",
        run_id="run-1",
        created_at_ms=1_700_000_000_000,
        balances=(BalanceSnapshot("USDT", Decimal("1000"), Decimal("900")),),
        positions=(PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("500")),),
    )
    external = AccountSnapshot(
        snapshot_id="external-1",
        source="paper_exchange_snapshot",
        run_id="run-1",
        created_at_ms=1_700_000_000_000,
        balances=(BalanceSnapshot("USDT", Decimal("950"), Decimal("900")),),
        positions=(
            PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("350")),
            PositionSnapshot("ETH/USDT", TradeSide.LONG, Decimal("100")),
        ),
    )

    report = reconcile_account_snapshots(
        report_id="recon-1",
        created_at_ms=1_700_000_000_001,
        internal=internal,
        external=external,
    )

    assert report.status is ReconciliationStatus.MISMATCHED
    assert [mismatch.code for mismatch in report.mismatches] == [
        "balance_total_mismatch",
        "position_notional_mismatch",
        "unexpected_external_position",
    ]
    assert [mismatch.severity.value for mismatch in report.mismatches] == ["warning", "critical", "critical"]
    record = report.to_record()
    assert record["schema_version"] == "reconciliation_report.v1"
    assert record["metadata"]["external_source"] == "paper_exchange_snapshot"


def _limits() -> AccountRiskLimits:
    return AccountRiskLimits(
        allowed_symbols=("BTC/USDT", "ETH/USDT"),
        position_limits=PositionLimitConfig(
            max_order_notional=Decimal("1000"),
            max_symbol_exposure=Decimal("1500"),
            max_total_exposure=Decimal("3000"),
        ),
        drawdown_limits=DrawdownLimits(
            max_peak_drawdown=Decimal("0.10"),
            max_daily_drawdown=Decimal("0.05"),
        ),
    )


def _state(
    *,
    current_equity: Decimal = Decimal("10000"),
    peak_equity: Decimal = Decimal("10000"),
    day_start_equity: Decimal = Decimal("10000"),
) -> AccountRiskState:
    return AccountRiskState(
        drawdown=DrawdownState(
            current_equity=current_equity,
            peak_equity=peak_equity,
            day_start_equity=day_start_equity,
        )
    )


def _command(action: SupervisorControlAction) -> SupervisorControlCommand:
    return SupervisorControlCommand(
        command_id=f"{action.value}-1",
        run_id="run-1",
        action=action,
        reason="operator control test",
        actor="operator",
        created_at_ms=1_700_000_000_000,
    )


def _proposal() -> TradeProposal:
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
        notional=Decimal("500"),
        entry_price=Decimal("50000"),
        stop_loss_price=Decimal("47500"),
        confidence=Decimal("0.75"),
        rationale="deterministic breakout criteria passed",
        created_at_ms=1_700_000_000_000,
        valid_until_ms=1_700_000_060_000,
    )
