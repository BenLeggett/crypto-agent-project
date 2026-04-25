"""Safe placeholder entrypoint for the market data collector."""

from __future__ import annotations

SERVICE_NAME = "collector"


def main() -> int:
    """Boot the collector placeholder without external side effects."""
    print(f"{SERVICE_NAME} placeholder: no market data collection is configured yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
