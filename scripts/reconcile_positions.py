"""Emit deterministic account reconciliation reports from local snapshots."""

from __future__ import annotations

import argparse
import json
import time
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from apps.supervisor.reconciliation import (
    account_snapshot_from_record,
    empty_account_snapshot,
    reconcile_account_snapshots,
)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    internal = _load_snapshot(
        args.internal_snapshot,
        snapshot_id="internal-empty",
        source="internal_mock",
        run_id=args.run_id,
        created_at_ms=args.created_at_ms,
    )
    external = _load_snapshot(
        args.external_snapshot,
        snapshot_id="external-empty",
        source="external_mock",
        run_id=args.run_id,
        created_at_ms=args.created_at_ms,
    )
    report = reconcile_account_snapshots(
        report_id=args.report_id or _default_report_id(args.run_id, args.created_at_ms),
        created_at_ms=args.created_at_ms,
        internal=internal,
        external=external,
        balance_tolerance=Decimal(args.balance_tolerance),
        position_notional_tolerance=Decimal(args.position_notional_tolerance),
    )
    print(json.dumps(report.to_record(), sort_keys=True))
    return 0


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare internal and external account snapshots without exchange calls, "
            "credentials, or execution side effects."
        )
    )
    parser.add_argument("--run-id", default="manual-reconciliation", help="Run ID used for empty mock snapshots.")
    parser.add_argument("--report-id", default="", help="Optional stable reconciliation report ID.")
    parser.add_argument("--created-at-ms", type=int, default=_now_ms(), help="Millisecond timestamp for replay.")
    parser.add_argument("--internal-snapshot", default="", help="Path to internal account snapshot JSON.")
    parser.add_argument("--external-snapshot", default="", help="Path to external account snapshot JSON.")
    parser.add_argument("--balance-tolerance", default="0", help="Allowed balance total difference.")
    parser.add_argument("--position-notional-tolerance", default="0", help="Allowed position notional difference.")
    return parser.parse_args(argv)


def _load_snapshot(
    path_text: str,
    *,
    snapshot_id: str,
    source: str,
    run_id: str,
    created_at_ms: int,
):
    if not path_text:
        return empty_account_snapshot(
            snapshot_id=snapshot_id,
            source=source,
            run_id=run_id,
            created_at_ms=created_at_ms,
        )
    return account_snapshot_from_record(_read_json(Path(path_text)))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("snapshot JSON must contain an object")
    return payload


def _default_report_id(run_id: str, created_at_ms: int) -> str:
    return f"reconciliation-{run_id}-{created_at_ms}"


def _now_ms() -> int:
    return int(time.time() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
