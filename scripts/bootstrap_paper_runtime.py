"""Bootstrap local paper-mode runtime audit artifacts."""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

from libs.config import AppMode, ProjectConfig, load_config
from libs.event_packets import build_restart_packet, event_packet_to_jsonl_line
from libs.journal import JournalAppendResult, JournalRecord, JournalRecordType, append_journal_record

PAPER_RUNTIME_BOOTSTRAP_SCHEMA_VERSION = "paper_runtime_bootstrap.v1"
DEFAULT_SERVICES = ("freqtrade-dryrun", "decision-engine", "supervisor", "paper-audit-bootstrap")


@dataclass(frozen=True)
class PaperRuntimeBootstrapResult:
    """Result of one paper runtime bootstrap write."""

    run_id: str
    journal_append: JournalAppendResult
    packet_path: Path
    packet_id: str
    services: tuple[str, ...]

    def to_record(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "journal_append": self.journal_append.to_record(),
            "packet_path": str(self.packet_path),
            "packet_id": self.packet_id,
            "services": list(self.services),
        }


def bootstrap_paper_runtime(
    *,
    run_id: str,
    journal_path: str | Path,
    packet_path: str | Path,
    config_hash: str,
    created_at_ms: Optional[int] = None,
    services: Sequence[str] = DEFAULT_SERVICES,
    config: Optional[ProjectConfig] = None,
) -> PaperRuntimeBootstrapResult:
    """Validate paper config and append local restart/bootstrap audit records."""

    project_config = config or load_config()
    _validate_paper_runtime_config(project_config)
    timestamp_ms = _now_ms() if created_at_ms is None else created_at_ms
    service_names = tuple(services)
    if not service_names:
        raise ValueError("services must not be empty")

    payload = _bootstrap_payload(project_config, service_names)
    record_id = f"paper-runtime-bootstrap-{run_id}-{timestamp_ms}"
    journal_record = JournalRecord(
        record_id=record_id,
        run_id=run_id,
        created_at_ms=timestamp_ms,
        record_type=JournalRecordType.RESTART,
        source="paper_runtime",
        config_hash=config_hash,
        payload=payload,
        metadata={
            "mode": project_config.app.mode.value,
            "execution": project_config.app.execution,
        },
    )
    journal_append = append_journal_record(journal_path, journal_record)
    packet = build_restart_packet(
        run_id=run_id,
        restart_id=record_id,
        occurred_at_ms=timestamp_ms,
        restart=payload,
        source="paper_runtime",
    )
    packet_output_path = Path(packet_path)
    packet_output_path.parent.mkdir(parents=True, exist_ok=True)
    with packet_output_path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(event_packet_to_jsonl_line(packet))

    return PaperRuntimeBootstrapResult(
        run_id=run_id,
        journal_append=journal_append,
        packet_path=packet_output_path,
        packet_id=packet.packet_id,
        services=service_names,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    result = bootstrap_paper_runtime(
        run_id=args.run_id,
        journal_path=args.journal_path,
        packet_path=args.packet_path,
        config_hash=args.config_hash,
    )
    print(json.dumps(result.to_record(), sort_keys=True))
    return 0


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize local paper-mode journal and event packet streams.")
    parser.add_argument("--run-id", default=os.environ.get("PAPER_RUN_ID", "paper-local"))
    parser.add_argument(
        "--journal-path",
        default=os.environ.get("PAPER_JOURNAL_PATH", "data/journals/paper-runtime.jsonl"),
    )
    parser.add_argument(
        "--packet-path",
        default=os.environ.get("PAPER_EVENT_PACKET_PATH", "data/event_packets/paper-runtime.jsonl"),
    )
    parser.add_argument("--config-hash", default=os.environ.get("PAPER_CONFIG_HASH", "paper-local-config"))
    return parser.parse_args(list(argv) if argv is not None else None)


def _validate_paper_runtime_config(config: ProjectConfig) -> None:
    if config.app.mode is not AppMode.PAPER:
        raise ValueError("paper runtime requires app mode 'paper'")
    if config.app.execution != "dry_run":
        raise ValueError("paper runtime requires dry_run execution")
    if config.app.trading_foundation != "freqtrade":
        raise ValueError("paper runtime requires the freqtrade trading foundation")
    if config.app.live_execution_enabled:
        raise ValueError("paper runtime must not enable live execution")
    if not config.risk.enabled:
        raise ValueError("deterministic risk governor must remain enabled")
    if config.risk.live_execution_enabled:
        raise ValueError("paper runtime risk config must not enable live execution")


def _bootstrap_payload(config: ProjectConfig, services: tuple[str, ...]) -> dict[str, object]:
    return {
        "schema_version": PAPER_RUNTIME_BOOTSTRAP_SCHEMA_VERSION,
        "config_env": config.config_env,
        "mode": config.app.mode.value,
        "execution": config.app.execution,
        "trading_foundation": config.app.trading_foundation,
        "risk_enabled": config.risk.enabled,
        "live_execution_enabled": config.app.live_execution_enabled,
        "risk_live_execution_enabled": config.risk.live_execution_enabled,
        "freqtrade_config_path": "freqtrade/user_data/config.dryrun.json",
        "services": list(services),
    }


def _now_ms() -> int:
    return int(time.time() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
