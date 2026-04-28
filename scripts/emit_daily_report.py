"""Emit a local paper-mode daily report from audit artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.replay_event_packets import ReplayTimeline, build_replay_timeline

DAILY_REPORT_SCHEMA_VERSION = "paper_daily_report.v1"
DEFAULT_JOURNAL_PATH = "data/journals/paper-runtime.jsonl"
DEFAULT_PACKET_PATH = "data/event_packets/paper-runtime.jsonl"
DEFAULT_OUTPUT_PATH = "data/summaries/daily_report.json"

PROPOSAL_TYPES = frozenset({"proposal_generated", "proposal_rejected", "proposal_output"})
RISK_DECISION_TYPES = frozenset({"risk_decision", "risk_veto"})
FILL_TYPES = frozenset({"fill", "partial_fill"})
EXECUTION_TYPES = frozenset({"order_submitted", "order_rejected", "fill", "partial_fill", "stop_hit"})
OPERATOR_UPDATE_TYPES = frozenset({"operator_update", "operator_update_sent"})
INCIDENT_TYPES = frozenset(
    {
        "alert",
        "data_gap",
        "flatten_requested",
        "kill_switch_activated",
        "mismatch",
        "reconciliation_mismatch",
        "risk_freeze",
        "risk_veto",
    }
)


@dataclass(frozen=True)
class DailyReport:
    """One local paper-mode report artifact."""

    run_id: str
    generated_at_ms: int
    journal_paths: tuple[str, ...]
    packet_paths: tuple[str, ...]
    timeline: ReplayTimeline

    def to_record(self) -> dict[str, Any]:
        timeline_record = self.timeline.to_record()
        return {
            "schema_version": DAILY_REPORT_SCHEMA_VERSION,
            "run_id": self.run_id,
            "mode": "paper",
            "live_execution_approved": False,
            "generated_at_ms": self.generated_at_ms,
            "start_ms": self.timeline.start_ms,
            "end_ms": self.timeline.end_ms,
            "source_journal_paths": list(self.journal_paths),
            "source_packet_paths": list(self.packet_paths),
            "summary": _summary_from_timeline(self.timeline),
            "timeline": timeline_record,
            "notes": [
                "Local paper-mode report only.",
                "This artifact is promotion evidence input, not live trading approval.",
            ],
        }


def build_daily_report(
    *,
    journal_paths: Iterable[str | Path],
    packet_paths: Iterable[str | Path],
    run_id: str = "",
    start_ms: int | None = None,
    end_ms: int | None = None,
    generated_at_ms: int | None = None,
) -> DailyReport:
    """Build a report by replaying local journal and event packet artifacts."""

    resolved_journal_paths = tuple(str(Path(path)) for path in journal_paths)
    resolved_packet_paths = tuple(str(Path(path)) for path in packet_paths)
    timeline = build_replay_timeline(
        journal_paths=resolved_journal_paths,
        packet_paths=resolved_packet_paths,
        run_id=run_id,
        start_ms=start_ms,
        end_ms=end_ms,
    )
    return DailyReport(
        run_id=run_id,
        generated_at_ms=_now_ms() if generated_at_ms is None else generated_at_ms,
        journal_paths=resolved_journal_paths,
        packet_paths=resolved_packet_paths,
        timeline=timeline,
    )


def daily_report_to_json(report: DailyReport, *, pretty: bool = False) -> str:
    """Serialize a daily report for local review or artifact storage."""

    if pretty:
        return json.dumps(report.to_record(), indent=2, sort_keys=True)
    return json.dumps(report.to_record(), sort_keys=True, separators=(",", ":"))


def write_daily_report(report: DailyReport, output_path: str | Path, *, pretty: bool = True) -> Path:
    """Write a local report JSON artifact and return the resolved path."""

    path = Path(output_path)
    if path.exists() and path.is_dir():
        raise ValueError("output_path must be a file path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"{daily_report_to_json(report, pretty=pretty)}\n", encoding="utf-8")
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parse_args(argv)
    report = build_daily_report(
        journal_paths=args.journal_path,
        packet_paths=args.packet_path,
        run_id=args.run_id,
        start_ms=args.start_ms,
        end_ms=args.end_ms,
    )
    output_path = write_daily_report(report, args.output_path, pretty=args.pretty)
    print(json.dumps({"output_path": str(output_path), "summary": report.to_record()["summary"]}, sort_keys=True))
    return 0


def _parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build a local paper-mode daily report from append-only journals, "
            "event packets, and replay timelines. This command reads local "
            "artifacts only and never approves live execution."
        )
    )
    parser.add_argument(
        "--journal-path",
        action="append",
        default=[],
        help="Path to a journal JSONL file. May be supplied more than once.",
    )
    parser.add_argument(
        "--packet-path",
        action="append",
        default=[],
        help="Path to an event packet JSONL file. May be supplied more than once.",
    )
    parser.add_argument("--run-id", default=os.environ.get("PAPER_RUN_ID", "paper-local"))
    parser.add_argument("--start-ms", type=int, default=None, help="Inclusive millisecond timestamp lower bound.")
    parser.add_argument("--end-ms", type=int, default=None, help="Inclusive millisecond timestamp upper bound.")
    parser.add_argument(
        "--output-path",
        default=os.environ.get("PAPER_DAILY_REPORT_PATH", DEFAULT_OUTPUT_PATH),
        help="Path for the local report JSON artifact.",
    )
    parser.add_argument("--pretty", action="store_true", help="Write indented JSON.")
    parsed = parser.parse_args(list(argv) if argv is not None else None)
    parsed.journal_path = parsed.journal_path or [os.environ.get("PAPER_JOURNAL_PATH", DEFAULT_JOURNAL_PATH)]
    parsed.packet_path = parsed.packet_path or [os.environ.get("PAPER_EVENT_PACKET_PATH", DEFAULT_PACKET_PATH)]
    return parsed


def _summary_from_timeline(timeline: ReplayTimeline) -> dict[str, Any]:
    counts = Counter(item.event_type for item in timeline.items)
    return {
        "item_count": len(timeline.items),
        "journal_record_count": sum(1 for item in timeline.items if item.kind == "journal"),
        "event_packet_count": sum(1 for item in timeline.items if item.kind == "event_packet"),
        "event_type_counts": dict(sorted(counts.items())),
        "proposal_count": _sum_types(counts, PROPOSAL_TYPES),
        "risk_decision_count": _sum_types(counts, RISK_DECISION_TYPES),
        "risk_veto_count": counts.get("risk_veto", 0),
        "fill_count": _sum_types(counts, FILL_TYPES),
        "data_gap_count": counts.get("data_gap", 0),
        "reconciliation_mismatch_count": counts.get("reconciliation_mismatch", 0) + counts.get("mismatch", 0),
        "restart_count": counts.get("restart", 0),
        "operator_update_count": _sum_types(counts, OPERATOR_UPDATE_TYPES),
        "incident_count": _sum_types(counts, INCIDENT_TYPES),
        "execution_events_present": any(counts.get(event_type, 0) > 0 for event_type in EXECUTION_TYPES),
        "report_scope": "local_paper_audit_artifacts",
        "live_execution_approved": False,
    }


def _sum_types(counts: Counter[str], event_types: Iterable[str]) -> int:
    return sum(counts.get(event_type, 0) for event_type in event_types)


def _now_ms() -> int:
    return int(time.time() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
