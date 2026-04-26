"""Append-only local journal writer."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from libs.journal.schema import JournalRecord, canonical_journal_json, journal_record_from_mapping


@dataclass(frozen=True)
class JournalAppendResult:
    """Metadata returned after one append-only journal write."""

    path: Path
    record_id: str
    run_id: str
    line_number: int
    byte_offset: int
    content_hash: str

    def to_record(self) -> dict[str, str | int]:
        return {
            "path": str(self.path),
            "record_id": self.record_id,
            "run_id": self.run_id,
            "line_number": self.line_number,
            "byte_offset": self.byte_offset,
            "content_hash": self.content_hash,
        }


class JournalWriter:
    """Append validated records to a local JSONL journal file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def append(self, record: JournalRecord) -> JournalAppendResult:
        """Append one validated record and return deterministic write metadata."""

        if not isinstance(record, JournalRecord):
            raise TypeError("record must be a JournalRecord")
        if self.path.exists() and self.path.is_dir():
            raise ValueError("journal path must be a file path")

        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = canonical_journal_json(record)
        offset = self.path.stat().st_size if self.path.exists() else 0
        line_number = _existing_line_count(self.path) + 1
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line)
            handle.write("\n")
        return JournalAppendResult(
            path=self.path,
            record_id=record.record_id,
            run_id=record.run_id,
            line_number=line_number,
            byte_offset=offset,
            content_hash=_sha256_text(line),
        )


def append_journal_record(path: str | Path, record: JournalRecord) -> JournalAppendResult:
    """Convenience wrapper for appending a single journal record."""

    return JournalWriter(path).append(record)


def read_journal_records(path: str | Path) -> tuple[JournalRecord, ...]:
    """Read and validate all JSONL records from a local journal file."""

    journal_path = Path(path)
    if not journal_path.exists():
        return ()
    return tuple(_iter_journal_records(journal_path))


def _iter_journal_records(path: Path) -> Iterator[JournalRecord]:
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid journal JSON on line {line_number}") from exc
            if not isinstance(payload, dict):
                raise ValueError(f"journal line {line_number} must contain an object")
            yield journal_record_from_mapping(payload)


def _existing_line_count(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = [
    "JournalAppendResult",
    "JournalWriter",
    "append_journal_record",
    "read_journal_records",
]
