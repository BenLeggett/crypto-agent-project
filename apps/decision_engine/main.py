"""Safe placeholder entrypoint for the decision engine."""

from __future__ import annotations

from libs.common.logging import configure_logging, get_logger
from libs.config import load_config

SERVICE_NAME = "decision_engine"


def main() -> int:
    """Boot the decision engine placeholder without creating proposals."""
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)
    get_logger(__name__).info(
        "decision engine placeholder: no decision loop is configured yet.",
        extra={"event": "placeholder_started", "mode": config.app.mode.value},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
