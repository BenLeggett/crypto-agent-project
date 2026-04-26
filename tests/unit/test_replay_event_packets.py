from __future__ import annotations

import json

import pytest

from libs.event_packets import build_freeze_packet, build_proposal_packet, event_packet_to_jsonl_line
from libs.journal import JournalRecord, JournalRecordType, JournalWriter
from scripts.replay_event_packets import build_replay_timeline, main, timeline_to_json


def test_replay_timeline_orders_journals_and_event_packets_deterministically(tmp_path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    packet_path = tmp_path / "packets.jsonl"
    writer = JournalWriter(journal_path)
    writer.append(_journal_record(record_id="journal-late", created_at_ms=1_700_000_000_020))
    writer.append(_journal_record(record_id="journal-early", created_at_ms=1_700_000_000_000))
    packet_path.write_text(
        "".join(
            [
                event_packet_to_jsonl_line(
                    build_proposal_packet(
                        run_id="run-1",
                        proposal_id="proposal-1",
                        occurred_at_ms=1_700_000_000_010,
                        proposal={"symbol": "BTC/USDT"},
                    )
                ),
                event_packet_to_jsonl_line(
                    build_freeze_packet(
                        run_id="run-1",
                        command_id="freeze-1",
                        occurred_at_ms=1_700_000_000_020,
                        freeze={"entries_frozen": True},
                    )
                ),
            ]
        ),
        encoding="utf-8",
    )

    timeline = build_replay_timeline(journal_paths=[journal_path], packet_paths=[packet_path], run_id="run-1")

    assert [item.entity_id for item in timeline.items] == [
        "journal-early",
        "proposal-1",
        "journal-late",
        "freeze-1",
    ]
    assert [item.kind for item in timeline.items] == ["journal", "event_packet", "journal", "event_packet"]
    assert timeline.to_record()["item_count"] == 4


def test_replay_timeline_filters_by_run_id_and_date_range(tmp_path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    packet_path = tmp_path / "packets.jsonl"
    writer = JournalWriter(journal_path)
    writer.append(_journal_record(record_id="keep-journal", created_at_ms=1_700_000_000_010))
    writer.append(_journal_record(record_id="old-journal", created_at_ms=1_700_000_000_000))
    writer.append(_journal_record(record_id="other-run", run_id="run-2", created_at_ms=1_700_000_000_015))
    packet_path.write_text(
        event_packet_to_jsonl_line(
            build_proposal_packet(
                run_id="run-1",
                proposal_id="keep-packet",
                occurred_at_ms=1_700_000_000_020,
                proposal={"symbol": "BTC/USDT"},
            )
        ),
        encoding="utf-8",
    )

    timeline = build_replay_timeline(
        journal_paths=[journal_path],
        packet_paths=[packet_path],
        run_id="run-1",
        start_ms=1_700_000_000_005,
        end_ms=1_700_000_000_020,
    )

    assert [item.entity_id for item in timeline.items] == ["keep-journal", "keep-packet"]


def test_replay_cli_prints_compact_json(capsys, tmp_path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    JournalWriter(journal_path).append(_journal_record(record_id="record-1"))

    assert main(["--journal-path", str(journal_path), "--run-id", "run-1"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["run_id"] == "run-1"
    assert output["item_count"] == 1
    assert output["items"][0]["entity_id"] == "record-1"


def test_replay_rejects_invalid_time_range() -> None:
    with pytest.raises(ValueError, match="start_ms"):
        build_replay_timeline(start_ms=2, end_ms=1)


def test_replay_wraps_corrupt_packet_jsonl_with_path_and_line(tmp_path) -> None:
    packet_path = tmp_path / "bad-packets.jsonl"
    packet_path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="bad-packets.jsonl on line 1"):
        build_replay_timeline(packet_paths=[packet_path])


def test_timeline_to_json_supports_pretty_output(tmp_path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    JournalWriter(journal_path).append(_journal_record(record_id="record-1"))
    timeline = build_replay_timeline(journal_paths=[journal_path])

    assert "\n" in timeline_to_json(timeline, pretty=True)


def _journal_record(
    *,
    record_id: str = "record-1",
    run_id: str = "run-1",
    created_at_ms: int = 1_700_000_000_000,
) -> JournalRecord:
    return JournalRecord(
        record_id=record_id,
        run_id=run_id,
        created_at_ms=created_at_ms,
        record_type=JournalRecordType.RISK_DECISION,
        source="tests",
        config_hash="config-hash-1",
        payload={"allowed": False, "primary_reason": "entries_frozen"},
        metadata={"mode": "paper"},
    )
