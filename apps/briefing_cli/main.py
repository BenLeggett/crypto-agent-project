"""Safe placeholder entrypoint for the briefing CLI."""

from __future__ import annotations

SERVICE_NAME = "briefing_cli"


def main() -> int:
    """Boot the briefing CLI placeholder without invoking AI providers."""
    print(f"{SERVICE_NAME} placeholder: no briefing command is configured yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
