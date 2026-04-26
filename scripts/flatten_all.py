"""Emit deterministic flatten-workflow request records."""

from __future__ import annotations

import argparse
import json
import time
from typing import Optional

from apps.supervisor.kill_switch import build_flatten_workflow_request


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    request = build_flatten_workflow_request(
        request_id=args.request_id or _default_request_id(args.run_id, args.created_at_ms),
        run_id=args.run_id,
        reason=args.reason,
        actor=args.actor,
        created_at_ms=args.created_at_ms,
    )
    print(json.dumps(request.to_record(), sort_keys=True))
    return 0


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Request a flatten-all workflow without exchange execution or live wallet access."
    )
    parser.add_argument("--run-id", default="manual-control", help="Run ID attached to the flatten request.")
    parser.add_argument("--reason", required=True, help="Human-readable reason for requesting flatten.")
    parser.add_argument("--actor", default="operator", help="Actor requesting the flatten workflow.")
    parser.add_argument("--request-id", default="", help="Optional stable flatten request identifier.")
    parser.add_argument("--created-at-ms", type=int, default=_now_ms(), help="Millisecond timestamp for replay.")
    return parser.parse_args(argv)


def _default_request_id(run_id: str, created_at_ms: int) -> str:
    return f"flatten-all-{run_id}-{created_at_ms}"


def _now_ms() -> int:
    return int(time.time() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
