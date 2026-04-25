"""Safe placeholder entrypoint for the decision engine."""

from __future__ import annotations

SERVICE_NAME = "decision_engine"


def main() -> int:
    """Boot the decision engine placeholder without creating proposals."""
    print(f"{SERVICE_NAME} placeholder: no decision loop is configured yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
