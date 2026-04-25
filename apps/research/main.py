"""Safe placeholder entrypoint for offline research jobs."""

from __future__ import annotations

SERVICE_NAME = "research"


def main() -> int:
    """Boot the research placeholder without reading private data."""
    print(f"{SERVICE_NAME} placeholder: no research job is configured yet.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
