"""Reconstruct local decision and incident timelines from audit streams."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Literal, Optional

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from libs.event_packets import EventPacket, event_packet_from_jsonl_line
from libs.journal import JournalRecord, read_journal_records

ReplayItemKind = Literal["journal", "event_packet"]


@dataclass(frozen=True)
class ReplayTimelineItem:
    """One normalized replay item from a journal record or event packet."""

    kind: ReplayItemKind
    run_id: str
    occurred_at_ms: int
    source: str
    event_type: str
    entity_id: str
    record: dict[str, Any]

    def to_record(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "run_id": self.run_id,
            "occurred_at_ms": self.occurred_at_ms,
            "source": self.source,
            "event_type": self.event_type,
            "entity_id": self.entity_id,
            "record": self.record,
        }


@dataclass(frozen=True)
class ReplayTimeline:
    """A deterministic decision and incident timeline."""

    items: tuple[ReplayTimelineItem, ...]
    run_id: str = ""
    start_ms: int | None = None
    end_ms: int | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "item_count": len(self.items),
            "items": [item.to_record() for item in self.items],
        }


def build_replay_timeline(
    *,
    journal_paths: Iterable[str | Path] = (),
    packet_paths: Iterable[str | Path] = (),
    run_id: str = "",
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> ReplayTimeline:
    """Read local audit streams and return a deterministically ordered timeline."""

    if start_ms is not None and end_ms is not None and start_ms > end_ms:
        raise ValueError("start_ms must be less than or equal to end_ms")

    items: list[ReplayTimelineItem] = []
    for record in _read_journal_paths(journal_paths):
        item = _journal_item(record)
        if _matches_filters(item, run_id=run_id, start_ms=start_ms, end_ms=end_ms):
            items.append(item)
    for packet in _read_packet_paths(packet_paths):
        item = _packet_item(packet)
        if _matches_filters(item, run_id=run_id, start_ms=start_ms, end_ms=end_ms):
            items.append(item)

    return ReplayTimeline(
        items=tuple(sorted(items, key=_sort_key)),
        run_id=run_id,
        start_ms=start_ms,
        end_ms=end_ms,
    )


def timeline_to_json(timeline: ReplayTimeline, *, pretty: bool = False) -> str:
    """Serialize a replay timeline for operator review or downstream tooling."""

    if pretty:
        return json.dumps(timeline.to_record(), indent=2, sort_keys=True)
    return json.dumps(timeline.to_record(), sort_keys=True, separators=(",", ":"))


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    timeline = build_replay_timeline(
        journal_paths=args.journal_path,
        packet_paths=args.packet_path,
        run_id=args.run_id,
        start_ms=args.start_ms,
        end_ms=args.end_ms,
    )
    print(timeline_to_json(timeline, pretty=args.pretty))
    return 0


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Replay local append-only journal JSONL and event packet JSONL into an "
            "ordered decision/incident timeline. This command reads files only."
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
    parser.add_argument("--run-id", default="", help="Optional run ID filter.")
    parser.add_argument("--start-ms", type=int, default=None, help="Inclusive millisecond timestamp lower bound.")
    parser.add_argument("--end-ms", type=int, default=None, help="Inclusive millisecond timestamp upper bound.")
    parser.add_argument("--pretty", action="store_true", help="Print indented JSON.")
    return parser.parse_args(argv)


def _read_journal_paths(paths: Iterable[str | Path]) -> tuple[JournalRecord, ...]:
    records: list[JournalRecord] = []
    for path in paths:
        records.extend(read_journal_records(path))
    return tuple(records)


def _read_packet_paths(paths: Iterable[str | Path]) -> tuple[EventPacket, ...]:
    packets: list[EventPacket] = []
    for path_value in paths:
        path = Path(path_value)
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    packets.append(event_packet_from_jsonl_line(stripped))
                except (json.JSONDecodeError, TypeError, ValueError) as exc:
                    raise ValueError(f"invalid event packet JSONL in {path} on line {line_number}") from exc
    return tuple(packets)


def _journal_item(record: JournalRecord) -> ReplayTimelineItem:
    return ReplayTimelineItem(
        kind="journal",
        run_id=record.run_id,
        occurred_at_ms=record.created_at_ms,
        source=record.source,
        event_type=record.record_type.value,
        entity_id=record.record_id,
        record=record.to_record(),
    )


def _packet_item(packet: EventPacket) -> ReplayTimelineItem:
    return ReplayTimelineItem(
        kind="event_packet",
        run_id=packet.run_id,
        occurred_at_ms=packet.occurred_at_ms,
        source=packet.source,
        event_type=packet.event_type.value,
        entity_id=packet.entity_id,
        record=packet.to_record(),
    )


def _matches_filters(
    item: ReplayTimelineItem,
    *,
    run_id: str,
    start_ms: int | None,
    end_ms: int | None,
) -> bool:
    if run_id and item.run_id != run_id:
        return False
    if start_ms is not None and item.occurred_at_ms < start_ms:
        return False
    if end_ms is not None and item.occurred_at_ms > end_ms:
        return False
    return True


def _sort_key(item: ReplayTimelineItem) -> tuple[int, int, str, str, str]:
    kind_order = 0 if item.kind == "journal" else 1
    return (item.occurred_at_ms, kind_order, item.source, item.event_type, item.entity_id)


if __name__ == "__main__":
    raise SystemExit(main())
