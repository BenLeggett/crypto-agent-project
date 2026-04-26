from __future__ import annotations

import json

import pytest

from libs.event_packets import (
    EventPacket,
    EventPacketSeverity,
    EventPacketType,
    build_fill_packet,
    build_freeze_packet,
    build_proposal_packet,
    build_reconciliation_mismatch_packet,
    build_reject_packet,
    build_restart_packet,
    build_risk_decision_packet,
    event_packet_from_json,
    event_packet_from_jsonl_line,
    event_packet_to_json,
    event_packet_to_jsonl_line,
)


def test_event_packet_schema_validates_and_serializes() -> None:
    packet = EventPacket(
        packet_id="packet-1",
        run_id="run-1",
        event_type=EventPacketType.PROPOSAL_GENERATED,
        occurred_at_ms=1_700_000_000_000,
        source="decision_engine",
        entity_id="proposal-1",
        severity=EventPacketSeverity.INFO,
        payload={"symbol": "BTC/USDT"},
        metadata={"mode": "paper"},
    )

    record = packet.to_record()
    encoded = event_packet_to_json(packet)
    decoded = event_packet_from_json(encoded)

    assert record["schema_version"] == "event_packet.v1"
    assert record["event_type"] == "proposal_generated"
    assert json.loads(encoded)["packet_id"] == "packet-1"
    assert decoded == packet


def test_event_packet_rejects_invalid_required_fields_and_payloads() -> None:
    with pytest.raises(ValueError, match="run_id"):
        _packet(run_id="")
    with pytest.raises(TypeError, match="event_type"):
        EventPacket(
            packet_id="packet-1",
            run_id="run-1",
            event_type="proposal_generated",  # type: ignore[arg-type]
            occurred_at_ms=1_700_000_000_000,
            source="decision_engine",
            entity_id="proposal-1",
            severity=EventPacketSeverity.INFO,
            payload={},
        )
    with pytest.raises(TypeError, match="JSON serializable"):
        _packet(payload={"bad": object()})
    with pytest.raises(ValueError, match="non-empty JSON"):
        event_packet_from_json("")


def test_proposal_and_risk_decision_builders_choose_event_types_and_severity() -> None:
    generated = build_proposal_packet(
        run_id="run-1",
        proposal_id="proposal-1",
        occurred_at_ms=1_700_000_000_000,
        proposal={"symbol": "BTC/USDT"},
    )
    rejected = build_proposal_packet(
        run_id="run-1",
        proposal_id="proposal-2",
        occurred_at_ms=1_700_000_000_001,
        proposal={"symbol": "ETH/USDT"},
        rejected=True,
        reason="stale_data",
    )
    allowed = build_risk_decision_packet(
        run_id="run-1",
        decision_id="decision-1",
        occurred_at_ms=1_700_000_000_002,
        risk_decision={"allowed": True},
        allowed=True,
    )
    veto = build_risk_decision_packet(
        run_id="run-1",
        decision_id="decision-2",
        occurred_at_ms=1_700_000_000_003,
        risk_decision={"allowed": False, "primary_reason": "entries_frozen"},
        allowed=False,
    )

    assert generated.event_type is EventPacketType.PROPOSAL_GENERATED
    assert generated.severity is EventPacketSeverity.INFO
    assert rejected.event_type is EventPacketType.PROPOSAL_REJECTED
    assert rejected.severity is EventPacketSeverity.WARNING
    assert rejected.metadata["reason"] == "stale_data"
    assert allowed.event_type is EventPacketType.RISK_DECISION
    assert allowed.metadata["allowed"] == "true"
    assert veto.event_type is EventPacketType.RISK_VETO
    assert veto.severity is EventPacketSeverity.WARNING


def test_execution_and_runtime_builders_cover_fills_rejects_restarts_and_freezes() -> None:
    fill = build_fill_packet(
        run_id="run-1",
        fill_id="fill-1",
        occurred_at_ms=1_700_000_000_000,
        fill={"symbol": "BTC/USDT", "quantity": "0.01"},
    )
    partial = build_fill_packet(
        run_id="run-1",
        fill_id="fill-2",
        occurred_at_ms=1_700_000_000_001,
        fill={"symbol": "BTC/USDT", "quantity": "0.005"},
        partial=True,
    )
    reject = build_reject_packet(
        run_id="run-1",
        reject_id="reject-1",
        occurred_at_ms=1_700_000_000_002,
        reject={"reason": "paper_exchange_reject"},
    )
    restart = build_restart_packet(
        run_id="run-1",
        restart_id="restart-1",
        occurred_at_ms=1_700_000_000_003,
        restart={"service": "supervisor"},
    )
    freeze = build_freeze_packet(
        run_id="run-1",
        command_id="freeze-1",
        occurred_at_ms=1_700_000_000_004,
        freeze={"entries_frozen": True},
    )
    kill = build_freeze_packet(
        run_id="run-1",
        command_id="kill-1",
        occurred_at_ms=1_700_000_000_005,
        freeze={"kill_switch_active": True},
        kill_switch=True,
    )

    assert fill.event_type is EventPacketType.FILL
    assert partial.event_type is EventPacketType.PARTIAL_FILL
    assert partial.metadata["partial"] == "true"
    assert reject.event_type is EventPacketType.ORDER_REJECTED
    assert reject.severity is EventPacketSeverity.WARNING
    assert restart.event_type is EventPacketType.RESTART
    assert freeze.event_type is EventPacketType.RISK_FREEZE
    assert freeze.severity is EventPacketSeverity.WARNING
    assert kill.event_type is EventPacketType.KILL_SWITCH_ACTIVATED
    assert kill.severity is EventPacketSeverity.CRITICAL


def test_reconciliation_builder_and_jsonl_round_trip() -> None:
    packet = build_reconciliation_mismatch_packet(
        run_id="run-1",
        report_id="recon-1",
        occurred_at_ms=1_700_000_000_000,
        report={"mismatches": [{"code": "position_notional_mismatch"}]},
        critical=True,
    )

    line = event_packet_to_jsonl_line(packet)
    decoded = event_packet_from_jsonl_line(line)

    assert packet.event_type is EventPacketType.RECONCILIATION_MISMATCH
    assert packet.severity is EventPacketSeverity.CRITICAL
    assert packet.metadata["critical"] == "true"
    assert line.endswith("\n")
    assert decoded == packet


def _packet(
    *,
    run_id: str = "run-1",
    payload: dict = None,
) -> EventPacket:
    return EventPacket(
        packet_id="packet-1",
        run_id=run_id,
        event_type=EventPacketType.PROPOSAL_GENERATED,
        occurred_at_ms=1_700_000_000_000,
        source="decision_engine",
        entity_id="proposal-1",
        severity=EventPacketSeverity.INFO,
        payload={"symbol": "BTC/USDT"} if payload is None else payload,
    )
