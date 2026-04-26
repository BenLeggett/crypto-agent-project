from __future__ import annotations

from decimal import Decimal

from apps.decision_engine.service import build_decision_audit_artifacts
from apps.supervisor.kill_switch import (
    build_flatten_workflow_request,
    control_command_audit_artifacts,
    flatten_workflow_audit_artifacts,
)
from apps.supervisor.reconciliation import (
    AccountSnapshot,
    BalanceSnapshot,
    PositionSnapshot,
    reconciliation_audit_artifacts,
    reconcile_account_snapshots,
)
from apps.supervisor.service import SupervisorConfig, SupervisorService
from libs.decisioning.deterministic_rules import DeterministicDecisionResult
from libs.decisioning.schemas import (
    DecisionInput,
    DecisionMode,
    MarketSnapshot,
    OrderIntentType,
    ProposalAction,
    SignalSource,
    TradeProposal,
)
from libs.event_packets import EventPacketType
from libs.journal import JournalRecordType
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


def test_decision_result_emits_journal_records_and_proposal_packet() -> None:
    result = DeterministicDecisionResult(decision_input=_decision_input(), output=_proposal())

    artifacts = build_decision_audit_artifacts(result)

    assert [record.record_type for record in artifacts.journal_records] == [
        JournalRecordType.PROPOSAL_INPUT,
        JournalRecordType.PROPOSAL_OUTPUT,
    ]
    assert artifacts.journal_records[0].config_hash == "config-hash-1"
    assert artifacts.event_packets[0].event_type is EventPacketType.PROPOSAL_GENERATED
    assert artifacts.event_packets[0].entity_id == "proposal-1"


def test_supervisor_evaluation_emits_risk_journal_and_veto_packet() -> None:
    service = SupervisorService(SupervisorConfig(_limits(), config_hash="risk-config-1"))

    artifacts = service.evaluate_proposal_with_audit(_proposal(), _state(entries_frozen=True))

    assert artifacts.evaluation.accepted is False
    assert artifacts.journal_records[0].record_type is JournalRecordType.RISK_DECISION
    assert artifacts.journal_records[0].config_hash == "risk-config-1"
    assert artifacts.event_packets[0].event_type is EventPacketType.RISK_VETO
    assert artifacts.event_packets[0].metadata["allowed"] == "false"


def test_supervisor_controls_and_flatten_emit_audit_artifacts() -> None:
    command = SupervisorControlCommand(
        command_id="freeze-1",
        run_id="run-1",
        action=SupervisorControlAction.FREEZE_ENTRIES,
        reason="paper drawdown review",
        actor="operator",
        created_at_ms=1_700_000_000_000,
    )
    state = apply_control_command(FreezeState(), command)
    freeze = control_command_audit_artifacts(command=command, state=state, config_hash="risk-config-1")
    flatten_request = build_flatten_workflow_request(
        request_id="flatten-1",
        run_id="run-1",
        reason="paper safety drill",
        actor="operator",
        created_at_ms=1_700_000_000_001,
        state=state,
    )
    flatten = flatten_workflow_audit_artifacts(request=flatten_request, config_hash="risk-config-1")

    assert freeze.journal_records[0].record_type is JournalRecordType.FREEZE
    assert freeze.event_packets[0].event_type is EventPacketType.RISK_FREEZE
    assert flatten.journal_records[0].record_type is JournalRecordType.SUPERVISOR_ACTION
    assert flatten.event_packets[0].event_type is EventPacketType.FLATTEN_REQUESTED
    assert flatten.event_packets[0].metadata["execution_enabled"] == "false"


def test_reconciliation_mismatch_emits_audit_artifacts_but_match_does_not() -> None:
    internal = _account_snapshot("internal-1", Decimal("500"))
    matched = reconcile_account_snapshots(
        report_id="matched-1",
        created_at_ms=1_700_000_000_001,
        internal=internal,
        external=_account_snapshot("external-1", Decimal("500")),
    )
    mismatched = reconcile_account_snapshots(
        report_id="mismatch-1",
        created_at_ms=1_700_000_000_002,
        internal=internal,
        external=_account_snapshot("external-2", Decimal("350")),
    )

    matched_artifacts = reconciliation_audit_artifacts(report=matched, config_hash="risk-config-1")
    mismatch_artifacts = reconciliation_audit_artifacts(report=mismatched, config_hash="risk-config-1")

    assert matched_artifacts.journal_records == ()
    assert matched_artifacts.event_packets == ()
    assert mismatch_artifacts.journal_records[0].record_type is JournalRecordType.MISMATCH
    assert mismatch_artifacts.event_packets[0].event_type is EventPacketType.RECONCILIATION_MISMATCH


def _decision_input() -> DecisionInput:
    market = MarketSnapshot(
        snapshot_id="market-1",
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp_ms=1_700_000_000_000,
        mark_price=Decimal("50000"),
        source="test",
    )
    return DecisionInput(
        decision_id="decision-1",
        run_id="run-1",
        mode=DecisionMode.PAPER,
        market=market,
        config_hash="config-hash-1",
        created_at_ms=1_700_000_000_000,
        allowed_symbols=("BTC/USDT",),
        source=SignalSource.DETERMINISTIC,
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


def _account_snapshot(snapshot_id: str, notional: Decimal) -> AccountSnapshot:
    return AccountSnapshot(
        snapshot_id=snapshot_id,
        source="test",
        run_id="run-1",
        created_at_ms=1_700_000_000_000,
        balances=(BalanceSnapshot("USDT", Decimal("1000"), Decimal("900")),),
        positions=(PositionSnapshot("BTC/USDT", TradeSide.LONG, notional),),
    )
