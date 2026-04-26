from __future__ import annotations

from decimal import Decimal

from apps.supervisor.alerts import (
    MockSupervisorAlertSink,
    SupervisorAlert,
    SupervisorAlertSeverity,
    SupervisorAlertType,
    alert_from_control_command,
    alert_from_flatten_request,
    alert_from_reconciliation_report,
    alerts_from_supervisor_evaluation,
    deliver_supervisor_alert,
    deliver_supervisor_alerts,
)
from apps.supervisor.kill_switch import build_flatten_workflow_request
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


def test_evaluation_alerts_cover_risk_veto_and_degraded_health() -> None:
    service = SupervisorService(SupervisorConfig(_limits()))
    evaluation = service.evaluate_proposal(_proposal(), _state(entries_frozen=True))

    alerts = alerts_from_supervisor_evaluation(evaluation, created_at_ms=1_700_000_000_999)

    assert [alert.alert_type for alert in alerts] == [
        SupervisorAlertType.RISK_VETO,
        SupervisorAlertType.DEGRADED_HEALTH,
    ]
    assert [alert.severity for alert in alerts] == [
        SupervisorAlertSeverity.WARNING,
        SupervisorAlertSeverity.WARNING,
    ]
    assert alerts[0].payload["primary_reason"] == "entries_frozen"
    assert alerts[1].payload["status"] == "degraded"


def test_control_alerts_cover_freeze_and_kill_switch_activation() -> None:
    freeze_command = _command(SupervisorControlAction.FREEZE_ENTRIES, "freeze-1")
    frozen = apply_control_command(FreezeState(), freeze_command)
    kill_command = _command(SupervisorControlAction.ACTIVATE_KILL_SWITCH, "kill-1")
    killed = apply_control_command(frozen, kill_command)

    freeze_alert = alert_from_control_command(freeze_command, frozen)
    kill_alert = alert_from_control_command(kill_command, killed)

    assert freeze_alert is not None
    assert freeze_alert.alert_type is SupervisorAlertType.ENTRIES_FROZEN
    assert freeze_alert.severity is SupervisorAlertSeverity.WARNING
    assert freeze_alert.payload["state"]["entries_frozen"] is True
    assert kill_alert is not None
    assert kill_alert.alert_type is SupervisorAlertType.KILL_SWITCH_ACTIVATED
    assert kill_alert.severity is SupervisorAlertSeverity.CRITICAL
    assert kill_alert.payload["state"]["kill_switch_active"] is True


def test_flatten_alert_stays_non_executing_and_reconciliation_alerts_only_on_mismatch() -> None:
    flatten = build_flatten_workflow_request(
        request_id="flatten-1",
        run_id="run-1",
        reason="paper safety drill",
        actor="operator",
        created_at_ms=1_700_000_000_000,
    )
    matched_report = reconcile_account_snapshots(
        report_id="recon-matched",
        created_at_ms=1_700_000_000_001,
        internal=_snapshot("internal-1", "internal"),
        external=_snapshot("external-1", "external"),
    )
    mismatch_report = reconcile_account_snapshots(
        report_id="recon-mismatch",
        created_at_ms=1_700_000_000_002,
        internal=_snapshot("internal-2", "internal"),
        external=_snapshot(
            "external-2",
            "external",
            positions=(PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("700")),),
        ),
    )

    flatten_alert = alert_from_flatten_request(flatten)
    mismatch_alert = alert_from_reconciliation_report(mismatch_report)

    assert flatten_alert.alert_type is SupervisorAlertType.FLATTEN_REQUESTED
    assert flatten_alert.metadata["execution_enabled"] == "false"
    assert flatten_alert.payload["execution_enabled"] is False
    assert matched_report.status is ReconciliationStatus.MATCHED
    assert alert_from_reconciliation_report(matched_report) is None
    assert mismatch_alert is not None
    assert mismatch_alert.alert_type is SupervisorAlertType.RECONCILIATION_MISMATCH
    assert mismatch_alert.severity is SupervisorAlertSeverity.CRITICAL
    assert mismatch_alert.metadata["critical_mismatches"] == "1"


def test_mock_sink_records_alerts_and_delivery_failure_is_non_blocking() -> None:
    sink = MockSupervisorAlertSink()
    alert = SupervisorAlert(
        alert_id="alert-1",
        run_id="run-1",
        alert_type=SupervisorAlertType.RISK_VETO,
        severity=SupervisorAlertSeverity.WARNING,
        created_at_ms=1_700_000_000_000,
        summary="risk veto: entries_frozen",
        source_id="decision-1",
    )

    deliveries = deliver_supervisor_alerts((alert,), sink)
    failed = deliver_supervisor_alert(alert, _FailingSink())

    assert deliveries[0].delivered is True
    assert sink.records()[0]["alert_type"] == "risk_veto"
    assert failed.delivered is False
    assert failed.provider == "failing_sink"
    assert "simulated delivery failure" in failed.error


class _FailingSink:
    provider_name = "failing_sink"

    def send(self, alert: SupervisorAlert) -> None:
        raise RuntimeError("simulated delivery failure")


def _limits() -> AccountRiskLimits:
    return AccountRiskLimits(
        allowed_symbols=("BTC/USDT",),
        position_limits=PositionLimitConfig(
            max_order_notional=Decimal("1000"),
            max_symbol_exposure=Decimal("1500"),
            max_total_exposure=Decimal("3000"),
        ),
        drawdown_limits=DrawdownLimits(
            max_peak_drawdown=Decimal("0.20"),
            max_daily_drawdown=Decimal("0.10"),
        ),
    )


def _state(*, entries_frozen: bool = False) -> AccountRiskState:
    return AccountRiskState(
        drawdown=DrawdownState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("10000"),
            day_start_equity=Decimal("10000"),
        ),
        entries_frozen=entries_frozen,
    )


def _command(action: SupervisorControlAction, command_id: str) -> SupervisorControlCommand:
    return SupervisorControlCommand(
        command_id=command_id,
        run_id="run-1",
        action=action,
        reason="operator control test",
        actor="operator",
        created_at_ms=1_700_000_000_000,
    )


def _snapshot(
    snapshot_id: str,
    source: str,
    *,
    positions: tuple[PositionSnapshot, ...] = (PositionSnapshot("BTC/USDT", TradeSide.LONG, Decimal("500")),),
) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id=snapshot_id,
        source=source,
        run_id="run-1",
        created_at_ms=1_700_000_000_000,
        balances=(BalanceSnapshot("USDT", Decimal("1000"), Decimal("900")),),
        positions=positions,
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
