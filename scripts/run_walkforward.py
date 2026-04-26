"""Run local walk-forward evaluation over saved Freqtrade backtest artifacts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional, Sequence

from apps.research.reports import ResearchReportError, create_backtest_evaluation_artifact
from apps.research.walkforward import WalkForwardError, parse_split_spec, run_walk_forward_evaluation


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split",
        action="append",
        default=[],
        help="Repeatable split spec: id,path,train_start,train_end,test_start,test_end.",
    )
    parser.add_argument("--output-dir", default="data/summaries/research", help="Metrics output directory.")
    parser.add_argument("--strategy", help="Strategy name when backtest JSON contains multiple strategies.")
    parser.add_argument("--variant", default="deterministic_baseline", help="Evaluation variant label.")
    parser.add_argument("--run-id", help="Optional stable run ID for reproducible artifact paths.")
    parser.add_argument(
        "--backtest-result",
        help="Compatibility path: summarize one saved backtest result without walk-forward split metadata.",
    )
    args = parser.parse_args(tuple(argv or ()))

    if args.split:
        try:
            splits = tuple(parse_split_spec(value) for value in args.split)
            _, manifest_path = run_walk_forward_evaluation(
                splits=splits,
                output_dir=Path(args.output_dir),
                strategy_name=args.strategy,
                variant=args.variant,
                run_id=args.run_id,
            )
        except (WalkForwardError, ValueError) as exc:
            print(f"run_walkforward failed: {exc}", file=sys.stderr)
            return 1
        print(f"walk-forward manifest written: {manifest_path}")
        return 0

    if args.backtest_result:
        try:
            _, output_path = create_backtest_evaluation_artifact(
                backtest_result_path=Path(args.backtest_result),
                output_dir=Path(args.output_dir),
                strategy_name=args.strategy,
                variant=args.variant,
            )
        except (ResearchReportError, ValueError) as exc:
            print(f"run_walkforward failed: {exc}", file=sys.stderr)
            return 1
        print(f"research metrics written: {output_path}")
        return 0

    print("run_walkforward ready: pass --split for walk-forward evaluation or --backtest-result for one report.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
