from __future__ import annotations

import json
from dataclasses import replace

import pytest

from libs.config import load_config
from libs.event_packets import EventPacketType, event_packet_from_jsonl_line
from libs.journal import JournalRecordType, read_journal_records
from scripts.bootstrap_paper_runtime import bootstrap_paper_runtime, main


def test_bootstrap_paper_runtime_writes_restart_journal_and_packet(tmp_path) -> None:
    journal_path = tmp_path / "journals" / "paper.jsonl"
    packet_path = tmp_path / "event_packets" / "paper.jsonl"

    result = bootstrap_paper_runtime(
        run_id="paper-test",
        journal_path=journal_path,
        packet_path=packet_path,
        config_hash="paper-config-1",
        created_at_ms=1_700_000_000_000,
        config=load_config(environ={}),
    )

    records = read_journal_records(journal_path)
    packet = event_packet_from_jsonl_line(packet_path.read_text(encoding="utf-8"))

    assert result.run_id == "paper-test"
    assert records[0].record_type is JournalRecordType.RESTART
    assert records[0].run_id == "paper-test"
    assert records[0].config_hash == "paper-config-1"
    assert records[0].payload["mode"] == "paper"
    assert records[0].payload["execution"] == "dry_run"
    assert records[0].payload["freqtrade_config_path"] == "freqtrade/user_data/config.dryrun.json"
    assert packet.event_type is EventPacketType.RESTART
    assert packet.run_id == "paper-test"
    assert packet.payload["live_execution_enabled"] is False


def test_bootstrap_paper_runtime_rejects_live_or_disabled_risk_config(tmp_path) -> None:
    config = load_config(environ={})
    live_enabled = replace(config, app=replace(config.app, live_execution_enabled=True))
    risk_disabled = replace(config, risk=replace(config.risk, enabled=False))

    with pytest.raises(ValueError, match="live execution"):
        bootstrap_paper_runtime(
            run_id="paper-test",
            journal_path=tmp_path / "journal.jsonl",
            packet_path=tmp_path / "packets.jsonl",
            config_hash="paper-config-1",
            config=live_enabled,
        )
    with pytest.raises(ValueError, match="risk governor"):
        bootstrap_paper_runtime(
            run_id="paper-test",
            journal_path=tmp_path / "journal.jsonl",
            packet_path=tmp_path / "packets.jsonl",
            config_hash="paper-config-1",
            config=risk_disabled,
        )


def test_bootstrap_paper_runtime_cli_prints_result(capsys, tmp_path) -> None:
    journal_path = tmp_path / "journal.jsonl"
    packet_path = tmp_path / "packets.jsonl"

    assert main(
        [
            "--run-id",
            "paper-cli",
            "--journal-path",
            str(journal_path),
            "--packet-path",
            str(packet_path),
            "--config-hash",
            "paper-config-1",
        ]
    ) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["run_id"] == "paper-cli"
    assert output["journal_append"]["line_number"] == 1
    assert packet_path.exists()
