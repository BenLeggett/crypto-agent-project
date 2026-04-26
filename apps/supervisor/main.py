"""Safe entrypoint for the deterministic supervisor."""

from __future__ import annotations

from decimal import Decimal

from apps.supervisor.service import SupervisorConfig, SupervisorService
from libs.common.logging import configure_logging, get_logger
from libs.config import load_config
from libs.config.models import ProjectConfig
from libs.risk import AccountRiskLimits, AccountRiskState, DrawdownLimits, DrawdownState, PositionLimitConfig

SERVICE_NAME = "supervisor"


def main() -> int:
    """Boot the supervisor without exchange, model, notifier, or wallet access."""
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)
    service = _build_bootstrap_service(config)
    health = service.health(_bootstrap_state())
    get_logger(__name__).info(
        "supervisor booted with deterministic risk policy.",
        extra={
            "event": "supervisor_started",
            "mode": config.app.mode.value,
            "health": health.to_record(),
        },
    )
    return 0


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
    raise SystemExit(main())
