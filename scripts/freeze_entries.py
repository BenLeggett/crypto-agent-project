"""Emit deterministic supervisor entry-freeze control records."""

from __future__ import annotations

import argparse
import json
import time
from typing import Optional

from libs.risk import FreezeState, SupervisorControlAction, SupervisorControlCommand, apply_control_command


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    action = SupervisorControlAction.UNFREEZE_ENTRIES if args.unfreeze else SupervisorControlAction.FREEZE_ENTRIES
    command = SupervisorControlCommand(
        command_id=args.command_id or _default_command_id(action, args.run_id, args.created_at_ms),
        run_id=args.run_id,
        action=action,
        reason=args.reason,
        actor=args.actor,
        created_at_ms=args.created_at_ms,
        metadata={"execution_enabled": "false"},
    )
    state = apply_control_command(FreezeState(), command)
    print(json.dumps({"command": command.to_record(), "state": state.to_record()}, sort_keys=True))
    return 0


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Freeze or unfreeze new entries without placing orders.")
    parser.add_argument("--run-id", default="manual-control", help="Run ID attached to the control record.")
    parser.add_argument("--reason", required=True, help="Human-readable reason for the control action.")
    parser.add_argument("--actor", default="operator", help="Actor requesting the control action.")
    parser.add_argument("--command-id", default="", help="Optional stable command identifier.")
    parser.add_argument("--created-at-ms", type=int, default=_now_ms(), help="Millisecond timestamp for replay.")
    parser.add_argument("--unfreeze", action="store_true", help="Emit an unfreeze-entries command instead.")
    return parser.parse_args(argv)


def _default_command_id(action: SupervisorControlAction, run_id: str, created_at_ms: int) -> str:
    return f"{action.value}-{run_id}-{created_at_ms}"


def _now_ms() -> int:
    return int(time.time() * 1000)


if __name__ == "__main__":
    raise SystemExit(main())
