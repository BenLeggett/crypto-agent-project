from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Optional

from apps.decision_engine.proposal_builder import DeterministicProposalBuilder
from apps.decision_engine.validators import build_trade_proposal_validation_report, validate_trade_proposal
from libs.decisioning.deterministic_rules import DeterministicProposalConfig
from libs.decisioning.scoring import ProposalValidationPolicy
from libs.decisioning.schemas import ProposalRejectionReason, TradeProposal
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
from libs.strategy.signal_snapshot import SNAPSHOT_SCHEMA_VERSION


FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "decisioning"


def test_decision_engine_replays_saved_strategy_snapshot_to_expected_record() -> None:
    snapshot_record = _load_json("deterministic_entry_snapshot.json")
    expected_record = _load_json("deterministic_entry_decision_record.json")
    snapshot = _strategy_snapshot_from_record(snapshot_record)
    builder = DeterministicProposalBuilder(
        DeterministicProposalConfig(allowed_symbols=("BTC/USDT",), proposal_ttl_ms=60_000)
    )

    result = builder.build(snapshot)

    assert result.to_record() == expected_record
    assert result.decision_input.strategy_snapshot == snapshot_record
    assert isinstance(result.output, TradeProposal)
    assert not hasattr(result.output, "place_order")


def test_decision_engine_fixture_output_passes_validation_boundary() -> None:
    snapshot = _strategy_snapshot_from_record(_load_json("deterministic_entry_snapshot.json"))
    result = DeterministicProposalBuilder(
        DeterministicProposalConfig(allowed_symbols=("BTC/USDT",), proposal_ttl_ms=60_000)
    ).build(snapshot)

    proposal = result.output
    assert isinstance(proposal, TradeProposal)
    validated = validate_trade_proposal(
        proposal,
        decision_input=result.decision_input,
        policy=ProposalValidationPolicy(
            allowed_symbols=("BTC/USDT",),
            max_notional=Decimal("1000"),
            max_quantity=Decimal("10"),
            min_confidence=Decimal("0.5"),
        ),
        now_ms=1_700_000_010_000,
    )

    assert validated is proposal


def test_decision_engine_replay_failure_becomes_structured_rejection() -> None:
    snapshot = _strategy_snapshot_from_record(_load_json("deterministic_entry_snapshot.json"))
    result = DeterministicProposalBuilder(
        DeterministicProposalConfig(allowed_symbols=("BTC/USDT",), proposal_ttl_ms=60_000)
    ).build(snapshot)

    proposal = result.output
    assert isinstance(proposal, TradeProposal)
    report = build_trade_proposal_validation_report(
        proposal,
        decision_input=result.decision_input,
        policy=ProposalValidationPolicy(
            allowed_symbols=("BTC/USDT",),
            max_notional=Decimal("100"),
            max_quantity=Decimal("1"),
        ),
        now_ms=1_700_000_010_000,
    )
    rejections = report.to_rejections(created_at_ms=1_700_000_011_000)

    assert report.passed is False
    assert [issue.reason for issue in report.issues] == [
        ProposalRejectionReason.SIZE_INVALID,
        ProposalRejectionReason.SIZE_INVALID,
    ]
    assert [rejection.reason for rejection in rejections] == [
        ProposalRejectionReason.SIZE_INVALID,
        ProposalRejectionReason.SIZE_INVALID,
    ]
    assert {rejection.metadata["field"] for rejection in rejections} == {"notional", "quantity"}


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _strategy_snapshot_from_record(record: Mapping[str, Any]) -> StrategySnapshot:
    if record["schema_version"] != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("fixture must use strategy_snapshot.v1")

    symbol = record["symbol"]
    timeframe = record["timeframe"]
    return StrategySnapshot(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_ms=record["timestamp_ms"],
        config_hash=record["config_hash"],
        regime=RegimeAssessment(
            label=RegimeLabel(record["regime"]["label"]),
            confidence=Decimal(record["regime"]["confidence"]),
            as_of_ms=record["regime"]["as_of_ms"],
            reason=record["regime"]["reason"],
            metadata=record["regime"]["metadata"],
        ),
        entry=EntrySignal(
            symbol=symbol,
            timeframe=timeframe,
            action=EntryDecision(record["entry"]["action"]),
            side=_optional_side(record["entry"]["side"]),
            strength=Decimal(record["entry"]["strength"]),
            timestamp_ms=record["entry"]["timestamp_ms"],
            reason=record["entry"]["reason"],
            metadata=record["entry"]["metadata"],
        ),
        exit=ExitSignal(
            symbol=symbol,
            timeframe=timeframe,
            action=ExitDecision(record["exit"]["action"]),
            side=_optional_side(record["exit"]["side"]),
            strength=Decimal(record["exit"]["strength"]),
            timestamp_ms=record["exit"]["timestamp_ms"],
            reason=record["exit"]["reason"],
            metadata=record["exit"]["metadata"],
        ),
        sizing_input=_sizing_input_from_record(record["sizing_input"]),
        position_size=_position_size_from_record(record["position_size"]),
        stop_plan=_stop_plan_from_record(record["stop_plan"]),
        metadata=record["metadata"],
    )


def _optional_side(value: Optional[str]) -> Optional[TradeSide]:
    if value is None:
        return None
    return TradeSide(value)


def _sizing_input_from_record(record: Optional[Mapping[str, Any]]) -> Optional[SizingInput]:
    if record is None:
        return None
    return SizingInput(
        symbol=record["symbol"],
        side=TradeSide(record["side"]),
        equity=Decimal(record["equity"]),
        risk_fraction=Decimal(record["risk_fraction"]),
        entry_price=Decimal(record["entry_price"]),
        stop_price=Decimal(record["stop_price"]),
        max_position_value=Decimal(record["max_position_value"]),
    )


def _position_size_from_record(record: Optional[Mapping[str, Any]]) -> Optional[PositionSize]:
    if record is None:
        return None
    return PositionSize(
        symbol=record["symbol"],
        side=TradeSide(record["side"]),
        quantity=Decimal(record["quantity"]),
        notional=Decimal(record["notional"]),
        risk_amount=Decimal(record["risk_amount"]),
        reason=record["reason"],
        metadata=record["metadata"],
    )


def _stop_plan_from_record(record: Optional[Mapping[str, Any]]) -> Optional[StopPlan]:
    if record is None:
        return None
    take_profit_price = record["take_profit_price"]
    trailing_distance = record["trailing_distance"]
    return StopPlan(
        symbol=record["symbol"],
        side=TradeSide(record["side"]),
        stop_price=Decimal(record["stop_price"]),
        take_profit_price=None if take_profit_price is None else Decimal(take_profit_price),
        trailing_distance=None if trailing_distance is None else Decimal(trailing_distance),
        reason=record["reason"],
        metadata=record["metadata"],
    )
