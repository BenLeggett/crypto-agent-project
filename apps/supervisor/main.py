"""Safe placeholder entrypoint for the deterministic supervisor."""

from __future__ import annotations

SERVICE_NAME = "supervisor"


def main() -> int:
    """Boot the supervisor placeholder without exchange or wallet access."""
    print(f"{SERVICE_NAME} placeholder: no risk service is configured yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
