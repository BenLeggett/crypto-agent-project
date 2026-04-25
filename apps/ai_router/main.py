"""Safe placeholder entrypoint for the AI router."""

from __future__ import annotations

SERVICE_NAME = "ai_router"


def main() -> int:
    """Boot the AI router placeholder without making model calls."""
    print(f"{SERVICE_NAME} placeholder: no model provider is configured yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
