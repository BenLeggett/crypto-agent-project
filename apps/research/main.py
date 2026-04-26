"""Offline research entrypoint for local evidence generation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from apps.research.reports import ResearchReportError, create_backtest_evaluation_artifact
from libs.common.logging import configure_logging, get_logger
from libs.config import load_config

SERVICE_NAME = "research"


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run a local research helper or boot safely when no job is selected."""
    config = load_config()
    configure_logging(config, service_name=SERVICE_NAME)

    args = _build_parser().parse_args(tuple(argv or ()))
    if args.command is None:
        get_logger(__name__).info(
            "research ready: no research job was selected.",
            extra={"event": "placeholder_started", "mode": config.app.mode.value},
        )
        return 0

    if args.command == "backtest-report":
        try:
            evaluation, output_path = create_backtest_evaluation_artifact(
                backtest_result_path=Path(args.input),
                output_dir=Path(args.output_dir),
                strategy_name=args.strategy,
                variant=args.variant,
            )
        except (ResearchReportError, ValueError) as exc:
            print(f"research backtest-report failed: {exc}", file=sys.stderr)
            return 1
        get_logger(__name__).info(
            "research backtest report written",
            extra={
                "event": "research_backtest_report_written",
                "strategy_name": evaluation.strategy_name,
                "variant": evaluation.variant,
                "output_path": str(output_path),
            },
        )
        print(f"research backtest report written: {output_path}")
        return 0

    print(f"Unsupported research command: {args.command}", file=sys.stderr)
    return 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")

    report_parser = subparsers.add_parser(
        "backtest-report",
        help="Summarize a saved Freqtrade backtest JSON artifact into project metrics.",
    )
    report_parser.add_argument("--input", required=True, help="Saved Freqtrade backtest JSON path.")
    report_parser.add_argument("--output-dir", default="data/summaries/research", help="Metrics output directory.")
    report_parser.add_argument("--strategy", help="Strategy name when the backtest JSON contains multiple strategies.")
    report_parser.add_argument("--variant", default="deterministic_baseline", help="Evaluation variant label.")
    return parser


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
