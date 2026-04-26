from __future__ import annotations

import json
from decimal import Decimal

import pytest

from apps.supervisor.kill_switch import activate_kill_switch, build_flatten_workflow_request
from apps.supervisor.service import SupervisorConfig, SupervisorService
from libs.decisioning.schemas import DecisionMode, OrderIntentType, ProposalAction, SignalSource, TradeProposal
from libs.risk import (
    FreezeState,
    AccountRiskLimits,
    AccountRiskState,
    DrawdownLimits,
    DrawdownState,
    PositionLimitConfig,
    SupervisorControlAction,
    SupervisorControlCommand,
    apply_control_command,
)
from libs.strategy.interfaces import TradeSide
from scripts import flatten_all, freeze_entries


def test_freeze_command_blocks_entries_through_supervisor_controls() -> None:
    command = _command(SupervisorControlAction.FREEZE_ENTRIES)
    controls = apply_control_command(FreezeState(), command)
    evaluation = SupervisorService(SupervisorConfig(_limits())).evaluate_proposal_with_controls(
        _proposal(),
        _account_state(),
        controls,
    )

    assert controls.entries_frozen is True
    assert controls.flatten_requested is False
    assert evaluation.accepted is False
    assert evaluation.risk_decision.primary_reason == "entries_frozen"


def test_unfreeze_command_reopens_entries_without_clearing_kill_switch() -> None:
    frozen = apply_control_command(FreezeState(), _command(SupervisorControlAction.FREEZE_ENTRIES))
    unfrozen = apply_control_command(frozen, _command(SupervisorControlAction.UNFREEZE_ENTRIES))
    killed = apply_control_command(unfrozen, _command(SupervisorControlAction.ACTIVATE_KILL_SWITCH))
    after_unfreeze = apply_control_command(killed, _command(SupervisorControlAction.UNFREEZE_ENTRIES))

    assert unfrozen.entries_frozen is False
    assert after_unfreeze.entries_frozen is False
    assert after_unfreeze.kill_switch_active is True
    assert after_unfreeze.flatten_requested is True


def test_kill_switch_freezes_entries_and_requests_flatten() -> None:
    state = activate_kill_switch(
        command_id="kill-1",
        run_id="run-1",
        reason="operator safety drill",
        actor="operator",
        created_at_ms=1_700_000_000_000,
    )

    assert state.entries_frozen is True
    assert state.kill_switch_active is True
    assert state.flatten_requested is True
    assert state.to_record()["reason"] == "operator safety drill"


def test_flatten_workflow_request_does_not_enable_execution() -> None:
    request = build_flatten_workflow_request(
        request_id="flatten-1",
        run_id="run-1",
        reason="reduce paper exposure",
        actor="operator",
        created_at_ms=1_700_000_000_000,
    )

    record = request.to_record()
    assert record["schema_version"] == "flatten_workflow_request.v1"
    assert record["execution_enabled"] is False
    assert record["state"]["entries_frozen"] is True
    assert record["state"]["flatten_requested"] is True

    with pytest.raises(ValueError, match="must not enable execution"):
        type(request)(
            request_id="flatten-2",
            run_id="run-1",
            reason="invalid execution enable",
            actor="operator",
            created_at_ms=1_700_000_000_000,
            state=request.state,
            execution_enabled=True,
        )


def test_freeze_entries_script_emits_replayable_json(capsys: pytest.CaptureFixture[str]) -> None:
    result = freeze_entries.main(
        [
            "--run-id",
            "run-1",
            "--reason",
            "paper drawdown review",
            "--actor",
            "operator",
            "--command-id",
            "freeze-1",
            "--created-at-ms",
            "1700000000000",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["command"]["action"] == "freeze_entries"
    assert payload["state"]["entries_frozen"] is True
    assert payload["state"]["kill_switch_active"] is False


def test_flatten_all_script_emits_non_executing_workflow(capsys: pytest.CaptureFixture[str]) -> None:
    result = flatten_all.main(
        [
            "--run-id",
            "run-1",
            "--reason",
            "paper safety drill",
            "--actor",
            "operator",
            "--request-id",
            "flatten-1",
            "--created-at-ms",
            "1700000000000",
        ]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["request_id"] == "flatten-1"
    assert payload["execution_enabled"] is False
    assert payload["state"]["flatten_requested"] is True


def _command(action: SupervisorControlAction) -> SupervisorControlCommand:
    return SupervisorControlCommand(
        command_id=f"{action.value}-1",
        run_id="run-1",
        action=action,
        reason="operator control test",
        actor="operator",
        created_at_ms=1_700_000_000_000,
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


def _account_state() -> AccountRiskState:
    return AccountRiskState(
        drawdown=DrawdownState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("10000"),
            day_start_equity=Decimal("10000"),
        )
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
