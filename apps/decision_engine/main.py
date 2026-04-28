"""Safe placeholder entrypoint for the decision engine."""

from __future__ import annotations

import argparse
import sys
import time
from typing import Optional, Sequence

from libs.common.logging import configure_logging, get_logger
from libs.config import load_config

SERVICE_NAME = "decision_engine"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Boot the decision engine placeholder without creating proposals."""
    args = _parse_args([] if argv is None else argv)
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)
    logger = get_logger(__name__)
    logger.info(
        "decision engine placeholder: no decision loop is configured yet.",
        extra={"event": "placeholder_started", "mode": config.app.mode.value},
    )
    if args.watch:
        _watch(logger, heartbeat_interval_seconds=args.heartbeat_interval_seconds)
    return 0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Boot the paper decision-engine boundary.")
    parser.add_argument("--watch", action="store_true", help="Keep the service alive for compose supervision.")
    parser.add_argument("--heartbeat-interval-seconds", type=float, default=60.0)
    return parser.parse_args(list(argv))


def _watch(logger, *, heartbeat_interval_seconds: float) -> None:
    if heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat interval must be positive")
    while True:
        logger.info(
            "decision engine heartbeat: waiting for Task 37 paper loop wiring.",
            extra={"event": "decision_engine_heartbeat"},
        )
        time.sleep(heartbeat_interval_seconds)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
