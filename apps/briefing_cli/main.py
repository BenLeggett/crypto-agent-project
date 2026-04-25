"""Safe placeholder entrypoint for the briefing CLI."""

from __future__ import annotations

from libs.common.logging import configure_logging, get_logger
from libs.config import load_config

SERVICE_NAME = "briefing_cli"


def main() -> int:
    """Boot the briefing CLI placeholder without invoking AI providers."""
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)
    get_logger(__name__).info(
        "briefing cli placeholder: no briefing command is configured yet.",
        extra={"event": "placeholder_started", "mode": config.app.mode.value},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
