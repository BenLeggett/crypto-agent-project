"""Safe placeholder entrypoint for offline research jobs."""

from __future__ import annotations

from libs.common.logging import configure_logging, get_logger
from libs.config import load_config

SERVICE_NAME = "research"


def main() -> int:
    """Boot the research placeholder without reading private data."""
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)
    get_logger(__name__).info(
        "research placeholder: no research job is configured yet.",
        extra={"event": "placeholder_started", "mode": config.app.mode.value},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
