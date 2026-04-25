"""Safe placeholder entrypoint for the deterministic supervisor."""

from __future__ import annotations

from libs.common.logging import configure_logging, get_logger
from libs.config import load_config

SERVICE_NAME = "supervisor"


def main() -> int:
    """Boot the supervisor placeholder without exchange or wallet access."""
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)
    get_logger(__name__).info(
        "supervisor placeholder: no risk service is configured yet.",
        extra={"event": "placeholder_started", "mode": config.app.mode.value},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
