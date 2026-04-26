"""Walk-forward evaluation over saved local backtest artifacts.

The runner records split metadata, per-split metric artifact paths, and compact
aggregate metrics. It consumes saved Freqtrade backtest outputs instead of
running exchange-backed jobs directly, so local validation needs no secrets.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from apps.research.reports import BacktestEvaluation, ResearchReportError, create_backtest_evaluation_artifact


WALK_FORWARD_SCHEMA_VERSION = "walk_forward_run.v1"


class WalkForwardError(RuntimeError):
    """Raised when a walk-forward run cannot be planned or written."""


@dataclass(frozen=True)
class WalkForwardSplit:
    """One train/test window and its saved backtest result."""

    split_id: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    backtest_result_path: Path

    def __post_init__(self) -> None:
        if not self.split_id:
            raise ValueError("split_id is required")
        for field_name, value in (
            ("train_start", self.train_start),
            ("train_end", self.train_end),
            ("test_start", self.test_start),
            ("test_end", self.test_end),
        ):
            if not value:
                raise ValueError(f"{field_name} is required")
        if _date_key(self.train_start) > _date_key(self.train_end):
            raise ValueError("train_start must be before or equal to train_end")
        if _date_key(self.test_start) > _date_key(self.test_end):
            raise ValueError("test_start must be before or equal to test_end")
        if _date_key(self.train_end) > _date_key(self.test_start):
            raise ValueError("train_end must be before or equal to test_start")

    def to_record(self) -> dict[str, str]:
        return {
            "split_id": self.split_id,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "backtest_result_path": str(self.backtest_result_path),
        }


@dataclass(frozen=True)
class WalkForwardSplitResult:
    """Evaluation output for one walk-forward split."""

    split: WalkForwardSplit
    evaluation: BacktestEvaluation
    metrics_artifact_path: Path

    def to_record(self, *, run_dir: Path) -> dict[str, Any]:
        return {
            **self.split.to_record(),
            "strategy_name": self.evaluation.strategy_name,
            "variant": self.evaluation.variant,
            "metrics_artifact_path": _relative_or_text(self.metrics_artifact_path, run_dir),
            "source_sha256": self.evaluation.source_sha256,
            "metrics": [metric.to_record() for metric in self.evaluation.metrics],
        }


@dataclass(frozen=True)
class WalkForwardRun:
    """Versioned manifest for a complete walk-forward evaluation run."""

    schema_version: str
    run_id: str
    generated_at: str
    variant: str
    output_dir: Path
    split_results: tuple[WalkForwardSplitResult, ...]
    aggregate_metrics: Mapping[str, str]
    notes: str = "Walk-forward evidence only; not live approval."

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "variant": self.variant,
            "output_dir": str(self.output_dir),
            "split_count": len(self.split_results),
            "split_results": [result.to_record(run_dir=self.output_dir) for result in self.split_results],
            "aggregate_metrics": dict(self.aggregate_metrics),
            "notes": self.notes,
        }


def run_walk_forward_evaluation(
    *,
    splits: Sequence[WalkForwardSplit],
    output_dir: Path,
    strategy_name: Optional[str] = None,
    variant: str = "deterministic_baseline",
    run_id: Optional[str] = None,
    generated_at: Optional[str] = None,
) -> tuple[WalkForwardRun, Path]:
    """Evaluate saved backtest artifacts for each split and write a manifest."""

    if not splits:
        raise WalkForwardError("at least one walk-forward split is required")
    if not variant:
        raise ValueError("variant is required")

    selected_generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    selected_run_id = run_id or _default_run_id(selected_generated_at)
    run_dir = output_dir / selected_run_id
    metrics_dir = run_dir / "metrics"
    split_results: list[WalkForwardSplitResult] = []

    for split in splits:
        split_variant = f"{variant}_{split.split_id}"
        try:
            evaluation, artifact_path = create_backtest_evaluation_artifact(
                backtest_result_path=split.backtest_result_path,
                output_dir=metrics_dir,
                strategy_name=strategy_name,
                variant=split_variant,
                generated_at=selected_generated_at,
            )
        except (ResearchReportError, ValueError) as exc:
            raise WalkForwardError(f"split {split.split_id} failed: {exc}") from exc
        split_results.append(
            WalkForwardSplitResult(split=split, evaluation=evaluation, metrics_artifact_path=artifact_path)
        )

    run = WalkForwardRun(
        schema_version=WALK_FORWARD_SCHEMA_VERSION,
        run_id=selected_run_id,
        generated_at=selected_generated_at,
        variant=variant,
        output_dir=run_dir,
        split_results=tuple(split_results),
        aggregate_metrics=_aggregate_metrics(split_results),
    )
    manifest_path = write_walk_forward_manifest(run)
    return run, manifest_path


def write_walk_forward_manifest(run: WalkForwardRun) -> Path:
    """Write the run manifest after all split artifacts are available."""

    run.output_dir.mkdir(parents=True, exist_ok=True)
    path = run.output_dir / "walk_forward_run.json"
    path.write_text(json.dumps(run.to_record(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def parse_split_spec(value: str) -> WalkForwardSplit:
    """Parse ``id,path,train_start,train_end,test_start,test_end`` CLI input."""

    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 6 or any(not part for part in parts):
        raise ValueError("split must be id,path,train_start,train_end,test_start,test_end")
    split_id, path, train_start, train_end, test_start, test_end = parts
    return WalkForwardSplit(
        split_id=split_id,
        backtest_result_path=Path(path),
        train_start=train_start,
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
    )


def _aggregate_metrics(results: Sequence[WalkForwardSplitResult]) -> dict[str, str]:
    split_count = Decimal(len(results))
    aggregate: dict[str, str] = {"split_count": str(len(results))}

    profit_values = _metric_values(results, "profit_total_ratio")
    if profit_values:
        aggregate["avg_profit_total_ratio"] = _decimal_to_text(sum(profit_values) / Decimal(len(profit_values)))
        aggregate["min_profit_total_ratio"] = _decimal_to_text(min(profit_values))
        aggregate["max_profit_total_ratio"] = _decimal_to_text(max(profit_values))

    drawdown_values = _metric_values(results, "max_drawdown_ratio")
    if drawdown_values:
        aggregate["avg_max_drawdown_ratio"] = _decimal_to_text(sum(drawdown_values) / Decimal(len(drawdown_values)))
        aggregate["worst_max_drawdown_ratio"] = _decimal_to_text(max(drawdown_values))

    trade_values = _metric_values(results, "total_trades")
    if trade_values:
        aggregate["total_trades"] = _decimal_to_text(sum(trade_values))
        aggregate["avg_trades_per_split"] = _decimal_to_text(sum(trade_values) / split_count)

    return aggregate


def _metric_values(results: Sequence[WalkForwardSplitResult], name: str) -> list[Decimal]:
    values: list[Decimal] = []
    for result in results:
        for metric in result.evaluation.metrics:
            if metric.name == name:
                values.append(metric.value)
                break
    return values


def _date_key(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return value
    try:
        return datetime.fromisoformat(value).date().isoformat().replace("-", "")
    except ValueError as exc:
        raise ValueError(f"invalid date value: {value!r}") from exc


def _default_run_id(generated_at: str) -> str:
    safe = "".join(char if char.isalnum() else "_" for char in generated_at)
    return f"walk_forward_{safe.strip('_')}"


def _relative_or_text(path: Path, base: Path) -> str:
    try:
        return str(path.relative_to(base))
    except ValueError:
        return str(path)


def _decimal_to_text(value: Decimal) -> str:
    rounded = value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
    if rounded == rounded.to_integral_value():
        return str(rounded.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return format(rounded.normalize(), "f")
