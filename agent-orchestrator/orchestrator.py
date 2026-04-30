from __future__ import annotations

import argparse
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for non-venv interpreters
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        _ = (args, kwargs)
        return False


def build_parser() -> argparse.ArgumentParser:
    """Create the Stage 1 CLI surface."""
    parser = argparse.ArgumentParser(description="Agent orchestrator scaffold.")
    parser.add_argument("--status", action="store_true", help="Show orchestrator status.")
    parser.add_argument("--run-next", action="store_true", help="Run the next task.")
    parser.add_argument("--phase-review", action="store_true", help="Review the current phase.")
    parser.add_argument("--validate", action="store_true", help="Run validation checks.")
    return parser


def main() -> int:
    """Load environment variables, parse CLI flags, and exit cleanly."""
    env_path = Path(__file__).with_name(".env")
    load_dotenv(env_path)
    build_parser().parse_args()
    print("Orchestrator ready")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
