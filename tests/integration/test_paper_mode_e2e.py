from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from apps.decision_engine.service import build_decision_audit_artifacts
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
from libs.event_packets import EventPacket, EventPacketSeverity, EventPacketType, build_event_packet
from libs.event_packets.serializers import event_packet_to_jsonl_line
from libs.journal import JournalRecord, JournalRecordType, append_journal_record, read_journal_records
from libs.market_data.quality_checks import validate_ohlcv_quality
from libs.market_data.storage import OHLCVDatasetRow
from libs.risk import AccountRiskLimits, AccountRiskState, DrawdownLimits, DrawdownState, PositionLimitConfig
from libs.strategy.interfaces import TradeSide
from scripts.bootstrap_paper_runtime import bootstrap_paper_runtime
from scripts.replay_event_packets import ReplayTimeline, build_replay_timeline


def test_paper_restart_recovery_appends_and_replays_bootstrap_artifacts(tmp_path) -> None:
    paths = _audit_paths(tmp_path)
    first = bootstrap_paper_runtime(
        run_id="paper-e2e",
        journal_path=paths["journal"],
        packet_path=paths["packets"],
        config_hash="paper-config-1",
        created_at_ms=1_700_000_000_000,
    )
    second = bootstrap_paper_runtime(
        run_id="paper-e2e",
        journal_path=paths["journal"],
        packet_path=paths["packets"],
        config_hash="paper-config-1",
        created_at_ms=1_700_000_060_000,
    )

    records = read_journal_records(paths["journal"])
    timeline = build_replay_timeline(
        journal_paths=[paths["journal"]],
        packet_paths=[paths["packets"]],
        run_id="paper-e2e",
    )

    assert first.journal_append.line_number == 1
    assert second.journal_append.line_number == 2
    assert [record.record_type for record in records] == [JournalRecordType.RESTART, JournalRecordType.RESTART]
    assert [item.event_type for item in timeline.items] == ["restart", "restart", "restart", "restart"]
    assert [item.occurred_at_ms for item in timeline.items] == [
        1_700_000_000_000,
        1_700_000_000_000,
        1_700_000_060_000,
        1_700_000_060_000,
    ]
    assert all(item.record["run_id"] == "paper-e2e" for item in timeline.items)


def test_paper_data_gap_is_blocked_and_replayable_without_execution(tmp_path) -> None:
    paths = _audit_paths(tmp_path)
    rows = (
        _ohlcv_row(timestamp_ms=1_700_000_000_000),
        _ohlcv_row(timestamp_ms=1_700_007_200_000),
    )
    report = validate_ohlcv_quality(rows, expected_interval_ms=3_600_000)
    gap_codes = [issue.code for issue in report.issues]

    assert report.passed is False
    assert "missing_candle_gap" in gap_codes

    data_gap_payload = {
        "quality_report": {
            "row_count": report.row_count,
            "issues": [issue.__dict__ for issue in report.issues],
        },
        "accepted_for_decisioning": False,
        "execution_enabled": False,
    }
    _append_journal_records(
        paths["journal"],
        [
            JournalRecord(
                record_id="market-data-gap-paper-e2e",
                run_id="paper-e2e",
                created_at_ms=1_700_007_200_000,
                record_type=JournalRecordType.MARKET_SNAPSHOT,
                source="collector",
                config_hash="paper-config-1",
                payload=data_gap_payload,
                metadata={"blocked_reason": "missing_candle_gap"},
            )
        ],
    )
    _append_event_packets(
        paths["packets"],
        [
            build_event_packet(
                event_type=EventPacketType.DATA_GAP,
                run_id="paper-e2e",
                occurred_at_ms=1_700_007_200_000,
                source="collector",
                entity_id="BTC/USDT:1h",
                severity=EventPacketSeverity.WARNING,
                payload=data_gap_payload,
                metadata={"execution_enabled": "false"},
            )
        ],
    )

    timeline = build_replay_timeline(
        journal_paths=[paths["journal"]],
        packet_paths=[paths["packets"]],
        run_id="paper-e2e",
    )

    assert _event_types(timeline) == ["market_snapshot", "data_gap"]
    assert all(event_type not in _event_types(timeline) for event_type in ("proposal_generated", "order_submitted", "fill"))


def test_paper_risk_veto_path_is_journaled_and_replayable(tmp_path) -> None:
    paths = _audit_paths(tmp_path)
    proposal = _proposal()
    decision_artifacts = build_decision_audit_artifacts(
        DeterministicDecisionResult(decision_input=_decision_input(), output=proposal)
    )
    supervisor = SupervisorService(SupervisorConfig(_limits(), config_hash="risk-config-1"))
    supervisor_artifacts = supervisor.evaluate_proposal_with_audit(proposal, _risk_state(entries_frozen=True))

    _append_journal_records(paths["journal"], decision_artifacts.journal_records)
    _append_event_packets(paths["packets"], decision_artifacts.event_packets)
    _append_journal_records(paths["journal"], supervisor_artifacts.journal_records)
    _append_event_packets(paths["packets"], supervisor_artifacts.event_packets)

    timeline = build_replay_timeline(
        journal_paths=[paths["journal"]],
        packet_paths=[paths["packets"]],
        run_id="paper-e2e",
    )

    assert supervisor_artifacts.evaluation.accepted is False
    assert supervisor_artifacts.evaluation.risk_decision.primary_reason == "entries_frozen"
    assert _event_types(timeline) == [
        "proposal_input",
        "proposal_output",
        "risk_decision",
        "proposal_generated",
        "risk_veto",
    ]
    assert all(event_type not in _event_types(timeline) for event_type in ("order_submitted", "fill"))


def test_paper_steady_state_is_dry_run_guarded_and_reviewable(tmp_path) -> None:
    paths = _audit_paths(tmp_path)
    bootstrap_paper_runtime(
        run_id="paper-e2e",
        journal_path=paths["journal"],
        packet_path=paths["packets"],
        config_hash="paper-config-1",
        created_at_ms=1_700_000_000_000,
    )
    supervisor = SupervisorService(SupervisorConfig(_limits(), config_hash="risk-config-1"))
    health = supervisor.health(_risk_state())
    dry_run_config = json.loads(Path("freqtrade/user_data/config.dryrun.json").read_text(encoding="utf-8"))
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    timeline = build_replay_timeline(
        journal_paths=[paths["journal"]],
        packet_paths=[paths["packets"]],
        run_id="paper-e2e",
    )

    assert dry_run_config["dry_run"] is True
    assert dry_run_config["exchange"]["key"] == ""
    assert dry_run_config["exchange"]["secret"] == ""
    assert "config.live.json" not in compose
    assert "LIVE_EXECUTION_ENABLED: \"false\"" in compose
    assert health.status.value == "ok"
    assert timeline.to_record()["item_count"] == 2
    assert _event_types(timeline) == ["restart", "restart"]


def _audit_paths(tmp_path) -> dict[str, Path]:
    return {
        "journal": tmp_path / "data" / "journals" / "paper-runtime.jsonl",
        "packets": tmp_path / "data" / "event_packets" / "paper-runtime.jsonl",
    }


def _append_journal_records(path: Path, records: tuple[JournalRecord, ...] | list[JournalRecord]) -> None:
    for record in records:
        append_journal_record(path, record)


def _append_event_packets(path: Path, packets: tuple[EventPacket, ...] | list[EventPacket]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for packet in packets:
            handle.write(event_packet_to_jsonl_line(packet))


def _event_types(timeline: ReplayTimeline) -> list[str]:
    return [item.event_type for item in timeline.items]


def _ohlcv_row(*, timestamp_ms: int) -> OHLCVDatasetRow:
    return OHLCVDatasetRow(
        symbol="BTC/USDT",
        timeframe="1h",
        timestamp_ms=timestamp_ms,
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("105"),
        volume=Decimal("1000"),
        source="fixture",
    )


def _decision_input() -> DecisionInput:
    market = MarketSnapshot(
        snapshot_id="market-1",
        symbol="BTC/USDT",
        timeframe="4h",
        timestamp_ms=1_700_000_000_000,
        mark_price=Decimal("50000"),
        source="paper-e2e",
    )
    return DecisionInput(
        decision_id="decision-1",
        run_id="paper-e2e",
        mode=DecisionMode.PAPER,
        market=market,
        config_hash="paper-config-1",
        created_at_ms=1_700_000_000_000,
        allowed_symbols=("BTC/USDT",),
        source=SignalSource.DETERMINISTIC,
    )


def _proposal() -> TradeProposal:
    return TradeProposal(
        proposal_id="proposal-1",
        decision_id="decision-1",
        run_id="paper-e2e",
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


def _risk_state(*, entries_frozen: bool = False) -> AccountRiskState:
    return AccountRiskState(
        drawdown=DrawdownState(
            current_equity=Decimal("10000"),
            peak_equity=Decimal("10000"),
            day_start_equity=Decimal("10000"),
        ),
        entries_frozen=entries_frozen,
    )
