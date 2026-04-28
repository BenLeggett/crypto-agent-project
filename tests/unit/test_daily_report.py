from __future__ import annotations

import json
from pathlib import Path

from libs.event_packets import build_event_packet, build_risk_decision_packet, event_packet_to_jsonl_line
from libs.event_packets.schemas import EventPacket, EventPacketSeverity, EventPacketType
from libs.journal import JournalRecord, JournalRecordType, append_journal_record
from scripts.emit_daily_report import build_daily_report, main, write_daily_report
from scripts.bootstrap_paper_runtime import bootstrap_paper_runtime


def test_daily_report_summarizes_local_paper_artifacts(tmp_path) -> None:
    paths = _audit_paths(tmp_path)
    bootstrap_paper_runtime(
        run_id="paper-report",
        journal_path=paths["journal"],
        packet_path=paths["packets"],
        config_hash="paper-config-1",
        created_at_ms=1_700_000_000_000,
    )
    append_journal_record(
        paths["journal"],
        JournalRecord(
            record_id="risk-veto-1",
            run_id="paper-report",
            created_at_ms=1_700_000_060_000,
            record_type=JournalRecordType.RISK_DECISION,
            source="supervisor",
            config_hash="paper-config-1",
            payload={"allowed": False, "reason": "entries_frozen"},
        ),
    )
    _append_packets(
        paths["packets"],
        [
            build_risk_decision_packet(
                run_id="paper-report",
                decision_id="risk-veto-1",
                occurred_at_ms=1_700_000_060_000,
                risk_decision={"allowed": False, "reason": "entries_frozen"},
                allowed=False,
            ),
            build_event_packet(
                event_type=EventPacketType.DATA_GAP,
                run_id="paper-report",
                occurred_at_ms=1_700_000_120_000,
                source="collector",
                entity_id="BTC/USDT:1h",
                severity=EventPacketSeverity.WARNING,
                payload={"accepted_for_decisioning": False},
            ),
        ],
    )

    report = build_daily_report(
        journal_paths=[paths["journal"]],
        packet_paths=[paths["packets"]],
        run_id="paper-report",
        generated_at_ms=1_700_000_180_000,
    )
    record = report.to_record()

    assert record["schema_version"] == "paper_daily_report.v1"
    assert record["mode"] == "paper"
    assert record["live_execution_approved"] is False
    assert record["summary"]["item_count"] == 5
    assert record["summary"]["journal_record_count"] == 2
    assert record["summary"]["event_packet_count"] == 3
    assert record["summary"]["restart_count"] == 2
    assert record["summary"]["risk_veto_count"] == 1
    assert record["summary"]["risk_decision_count"] == 2
    assert record["summary"]["data_gap_count"] == 1
    assert record["summary"]["incident_count"] == 2
    assert record["summary"]["execution_events_present"] is False
    assert "not live trading approval" in " ".join(record["notes"])


def test_daily_report_writes_artifact_and_cli_summary(tmp_path, capsys) -> None:
    paths = _audit_paths(tmp_path)
    output_path = tmp_path / "data" / "summaries" / "daily_report.json"
    bootstrap_paper_runtime(
        run_id="paper-cli",
        journal_path=paths["journal"],
        packet_path=paths["packets"],
        config_hash="paper-config-1",
        created_at_ms=1_700_000_000_000,
    )

    report = build_daily_report(
        journal_paths=[paths["journal"]],
        packet_paths=[paths["packets"]],
        run_id="paper-cli",
        generated_at_ms=1_700_000_060_000,
    )
    written = write_daily_report(report, output_path, pretty=True)

    assert written == output_path
    parsed = json.loads(output_path.read_text(encoding="utf-8"))
    assert parsed["summary"]["item_count"] == 2
    assert parsed["live_execution_approved"] is False

    result = main(
        [
            "--journal-path",
            str(paths["journal"]),
            "--packet-path",
            str(paths["packets"]),
            "--run-id",
            "paper-cli",
            "--output-path",
            str(output_path),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert result == 0
    assert stdout["output_path"] == str(output_path)
    assert stdout["summary"]["item_count"] == 2


def _audit_paths(tmp_path) -> dict[str, Path]:
    return {
        "journal": tmp_path / "data" / "journals" / "paper-runtime.jsonl",
        "packets": tmp_path / "data" / "event_packets" / "paper-runtime.jsonl",
    }


def _append_packets(path: Path, packets: list[EventPacket]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for packet in packets:
            handle.write(event_packet_to_jsonl_line(packet))
