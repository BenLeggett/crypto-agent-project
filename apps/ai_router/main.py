"""Safe placeholder entrypoint for the AI router."""

from __future__ import annotations

from libs.common.logging import configure_logging, get_logger
from libs.config import load_config

SERVICE_NAME = "ai_router"


def main() -> int:
    """Boot the AI router placeholder without making model calls."""
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)
    get_logger(__name__).info(
        "ai router placeholder: no model provider is configured yet.",
        extra={"event": "placeholder_started", "mode": config.app.mode.value},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
