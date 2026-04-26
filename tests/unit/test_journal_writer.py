from __future__ import annotations

import json

import pytest

from libs.journal import (
    JournalRecord,
    JournalRecordType,
    JournalWriter,
    canonical_journal_json,
    journal_record_from_mapping,
    read_journal_records,
)


def test_journal_record_validates_and_serializes_canonical_json() -> None:
    record = _record(payload={"symbol": "BTC/USDT", "allowed": False})

    payload = record.to_record()
    canonical = canonical_journal_json(record)

    assert payload["schema_version"] == "journal_record.v1"
    assert payload["record_type"] == "risk_decision"
    assert json.loads(canonical)["record_id"] == "record-1"
    assert journal_record_from_mapping(payload) == record


def test_journal_record_rejects_invalid_required_fields_and_payloads() -> None:
    with pytest.raises(ValueError, match="run_id"):
        _record(run_id="")
    with pytest.raises(ValueError, match="config_hash"):
        _record(config_hash="")
    with pytest.raises(TypeError, match="JSON serializable"):
        _record(payload={"bad": object()})
    with pytest.raises(TypeError, match="record_type"):
        JournalRecord(
            record_id="record-1",
            run_id="run-1",
            created_at_ms=1_700_000_000_000,
            record_type="risk_decision",  # type: ignore[arg-type]
            source="tests",
            config_hash="config-hash-1",
            payload={},
        )


def test_journal_writer_appends_jsonl_records_without_rewriting(tmp_path) -> None:
    path = tmp_path / "journals" / "run-1.jsonl"
    writer = JournalWriter(path)

    first = writer.append(_record(record_id="record-1", payload={"step": 1}))
    second = writer.append(
        _record(
            record_id="record-2",
            record_type=JournalRecordType.FREEZE,
            payload={"entries_frozen": True},
        )
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    records = read_journal_records(path)

    assert first.line_number == 1
    assert first.byte_offset == 0
    assert len(first.content_hash) == 64
    assert second.line_number == 2
    assert second.byte_offset > first.byte_offset
    assert len(lines) == 2
    assert json.loads(lines[0])["record_id"] == "record-1"
    assert json.loads(lines[1])["record_id"] == "record-2"
    assert [record.record_id for record in records] == ["record-1", "record-2"]


def test_read_journal_records_fails_on_corrupt_jsonl(tmp_path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid journal JSON"):
        read_journal_records(path)


def test_journal_writer_rejects_directory_path(tmp_path) -> None:
    with pytest.raises(ValueError, match="file path"):
        JournalWriter(tmp_path).append(_record())


def _record(
    *,
    record_id: str = "record-1",
    run_id: str = "run-1",
    record_type: JournalRecordType = JournalRecordType.RISK_DECISION,
    config_hash: str = "config-hash-1",
    payload: dict = None,
) -> JournalRecord:
    return JournalRecord(
        record_id=record_id,
        run_id=run_id,
        created_at_ms=1_700_000_000_000,
        record_type=record_type,
        source="tests",
        config_hash=config_hash,
        payload={"decision": "veto"} if payload is None else payload,
        metadata={"mode": "paper"},
    )
