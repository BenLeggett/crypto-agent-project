"""Safe entrypoint for the deterministic supervisor."""

from __future__ import annotations

import argparse
import sys
import time
from decimal import Decimal
from typing import Optional, Sequence

from apps.supervisor.service import SupervisorConfig, SupervisorService
from libs.common.logging import configure_logging, get_logger
from libs.config import load_config
from libs.config.models import ProjectConfig
from libs.risk import AccountRiskLimits, AccountRiskState, DrawdownLimits, DrawdownState, PositionLimitConfig

SERVICE_NAME = "supervisor"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Boot the supervisor without exchange, model, notifier, or wallet access."""
    args = _parse_args([] if argv is None else argv)
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)
    service = _build_bootstrap_service(config)
    health = service.health(_bootstrap_state())
    logger = get_logger(__name__)
    logger.info(
        "supervisor booted with deterministic risk policy.",
        extra={
            "event": "supervisor_started",
            "mode": config.app.mode.value,
            "health": health.to_record(),
        },
    )
    if args.watch:
        _watch(logger, service=service, heartbeat_interval_seconds=args.heartbeat_interval_seconds)
    return 0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Boot the deterministic supervisor boundary.")
    parser.add_argument("--watch", action="store_true", help="Keep the service alive for compose supervision.")
    parser.add_argument("--heartbeat-interval-seconds", type=float, default=60.0)
    return parser.parse_args(list(argv))


def _watch(logger, *, service: SupervisorService, heartbeat_interval_seconds: float) -> None:
    if heartbeat_interval_seconds <= 0:
        raise ValueError("heartbeat interval must be positive")
    while True:
        health = service.health(_bootstrap_state())
        logger.info(
            "supervisor heartbeat: deterministic risk policy loaded.",
            extra={"event": "supervisor_heartbeat", "health": health.to_record()},
        )
        time.sleep(heartbeat_interval_seconds)


def _build_bootstrap_service(config: ProjectConfig) -> SupervisorService:
    allowed_symbols = config.symbols.symbols or ("SUPERVISOR_BOOTSTRAP/USDT",)
    limits = AccountRiskLimits(
        allowed_symbols=allowed_symbols,
        position_limits=PositionLimitConfig(
            max_order_notional=Decimal("1"),
            max_symbol_exposure=Decimal("1"),
            max_total_exposure=Decimal("1"),
        ),
        drawdown_limits=DrawdownLimits(
            max_peak_drawdown=Decimal("0.01"),
            max_daily_drawdown=Decimal("0.01"),
        ),
        allow_future_live=False,
    )
    return SupervisorService(
        SupervisorConfig(
            account_limits=limits,
            service_name=SERVICE_NAME,
            risk_enabled=config.risk.enabled,
        )
    )


def _bootstrap_state() -> AccountRiskState:
    return AccountRiskState(
        drawdown=DrawdownState(
            current_equity=Decimal("1"),
            peak_equity=Decimal("1"),
            day_start_equity=Decimal("1"),
        ),
        open_positions=(),
        entries_frozen=False,
        kill_switch_active=False,
        metadata={"source": "supervisor_bootstrap"},
    )


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
