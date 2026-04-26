"""Research helpers for framework backtest outputs and evidence artifacts.

These helpers consume saved Freqtrade backtest JSON files and emit compact,
versioned metrics for later promotion review. They do not call exchanges,
models, wallets, or live execution paths.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence


RESEARCH_REPORT_SCHEMA_VERSION = "research_backtest_metrics.v1"


class ResearchReportError(RuntimeError):
    """Raised when a research report cannot be loaded or generated."""


@dataclass(frozen=True)
class FreqtradeBacktestRequest:
    """Explicit command shape for framework-backed research backtests."""

    config_path: Path = Path("freqtrade/user_data/config.dryrun.json")
    user_data_dir: Path = Path("freqtrade/user_data")
    strategy: str = "regime_breakout_strategy"
    command: str = "freqtrade"
    timerange: Optional[str] = None
    timeframe: Optional[str] = None
    export_filename: Optional[Path] = None

    def __post_init__(self) -> None:
        if not self.command:
            raise ValueError("command is required")
        if not self.strategy:
            raise ValueError("strategy is required")


@dataclass(frozen=True)
class BacktestMetric:
    """One reproducible metric extracted from a saved backtest artifact."""

    name: str
    value: Decimal
    unit: str

    def to_record(self) -> dict[str, str]:
        return {
            "name": self.name,
            "value": _decimal_to_text(self.value),
            "unit": self.unit,
        }


@dataclass(frozen=True)
class BacktestEvaluation:
    """Versioned evidence record for deterministic or model-informed variants."""

    schema_version: str
    source_framework: str
    source_path: str
    source_sha256: str
    strategy_name: str
    variant: str
    generated_at: str
    metrics: tuple[BacktestMetric, ...]
    backtest_start: Optional[str] = None
    backtest_end: Optional[str] = None
    notes: str = "Backtest evidence only; not live approval."

    def to_record(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source_framework": self.source_framework,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "strategy_name": self.strategy_name,
            "variant": self.variant,
            "generated_at": self.generated_at,
            "backtest_start": self.backtest_start,
            "backtest_end": self.backtest_end,
            "metrics": [metric.to_record() for metric in self.metrics],
            "notes": self.notes,
        }


def build_freqtrade_backtest_command(request: FreqtradeBacktestRequest) -> tuple[str, ...]:
    """Build a Freqtrade backtesting command without running it."""

    command = [
        request.command,
        "backtesting",
        "--config",
        str(request.config_path),
        "--userdir",
        str(request.user_data_dir),
        "--strategy",
        request.strategy,
        "--export",
        "trades",
    ]
    if request.timerange:
        command.extend(["--timerange", request.timerange])
    if request.timeframe:
        command.extend(["--timeframe", request.timeframe])
    if request.export_filename:
        command.extend(["--export-filename", str(request.export_filename)])
    return tuple(command)


def load_backtest_json(path: Path) -> Mapping[str, Any]:
    """Load a saved framework backtest JSON artifact."""

    if not path.is_file():
        raise ResearchReportError(f"Backtest result does not exist: {path}")
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ResearchReportError(f"Backtest result is not valid JSON: {path}") from exc
    if not isinstance(loaded, Mapping):
        raise ResearchReportError("Backtest result must be a JSON object")
    return loaded


def summarize_freqtrade_backtest(
    payload: Mapping[str, Any],
    *,
    source_path: Path,
    strategy_name: Optional[str] = None,
    variant: str = "deterministic_baseline",
    generated_at: Optional[str] = None,
    source_bytes: Optional[bytes] = None,
) -> BacktestEvaluation:
    """Extract deterministic metrics from a saved Freqtrade backtest payload."""

    if not variant:
        raise ValueError("variant is required")

    selected_strategy, strategy_payload = _select_strategy_payload(payload, strategy_name)
    metrics = _extract_metrics(strategy_payload)
    if not metrics:
        raise ResearchReportError("Backtest payload did not contain any supported metrics")

    return BacktestEvaluation(
        schema_version=RESEARCH_REPORT_SCHEMA_VERSION,
        source_framework="freqtrade",
        source_path=str(source_path),
        source_sha256=_sha256(source_bytes if source_bytes is not None else _stable_json_bytes(payload)),
        strategy_name=selected_strategy,
        variant=variant,
        generated_at=generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        backtest_start=_optional_text(strategy_payload.get("backtest_start")),
        backtest_end=_optional_text(strategy_payload.get("backtest_end")),
        metrics=tuple(sorted(metrics, key=lambda metric: metric.name)),
    )


def write_evaluation_artifact(evaluation: BacktestEvaluation, output_dir: Path) -> Path:
    """Write one versioned research metrics artifact to disk."""

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = "_".join(
        [
            _safe_slug(evaluation.variant),
            _safe_slug(evaluation.strategy_name),
            evaluation.source_sha256[:12],
        ]
    )
    path = output_dir / f"{filename}.json"
    path.write_text(json.dumps(evaluation.to_record(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def create_backtest_evaluation_artifact(
    *,
    backtest_result_path: Path,
    output_dir: Path,
    strategy_name: Optional[str] = None,
    variant: str = "deterministic_baseline",
    generated_at: Optional[str] = None,
) -> tuple[BacktestEvaluation, Path]:
    """Load a saved backtest result and write its research metrics artifact."""

    source_bytes = backtest_result_path.read_bytes() if backtest_result_path.is_file() else None
    payload = load_backtest_json(backtest_result_path)
    evaluation = summarize_freqtrade_backtest(
        payload,
        source_path=backtest_result_path,
        strategy_name=strategy_name,
        variant=variant,
        generated_at=generated_at,
        source_bytes=source_bytes,
    )
    return evaluation, write_evaluation_artifact(evaluation, output_dir)


def _select_strategy_payload(
    payload: Mapping[str, Any],
    strategy_name: Optional[str],
) -> tuple[str, Mapping[str, Any]]:
    strategy_section = payload.get("strategy")
    if isinstance(strategy_section, Mapping):
        if strategy_name:
            selected = strategy_section.get(strategy_name)
            if not isinstance(selected, Mapping):
                raise ResearchReportError(f"Strategy not found in backtest result: {strategy_name}")
            return strategy_name, selected
        if len(strategy_section) != 1:
            raise ResearchReportError("Backtest result contains multiple strategies; pass a strategy name")
        selected_name, selected_payload = next(iter(strategy_section.items()))
        if not isinstance(selected_payload, Mapping):
            raise ResearchReportError("Strategy payload must be a JSON object")
        return str(selected_name), selected_payload

    if strategy_name and isinstance(payload.get(strategy_name), Mapping):
        selected_payload = payload[strategy_name]
        if not isinstance(selected_payload, Mapping):
            raise ResearchReportError("Strategy payload must be a JSON object")
        return strategy_name, selected_payload

    selected_name = strategy_name or _optional_text(payload.get("strategy_name")) or "unknown_strategy"
    return selected_name, payload


def _extract_metrics(strategy_payload: Mapping[str, Any]) -> list[BacktestMetric]:
    metrics: list[BacktestMetric] = []

    total_trades = _decimal_from_any(strategy_payload.get("total_trades"))
    if total_trades is None:
        trades = strategy_payload.get("trades")
        if isinstance(trades, Sequence) and not isinstance(trades, (str, bytes, bytearray)):
            total_trades = Decimal(len(trades))
    _append_metric(metrics, "total_trades", total_trades, "count")

    wins = _decimal_from_any(strategy_payload.get("wins") or strategy_payload.get("winning_trades"))
    losses = _decimal_from_any(strategy_payload.get("losses") or strategy_payload.get("losing_trades"))
    if wins is None or losses is None:
        inferred_wins, inferred_losses = _wins_losses_from_trades(strategy_payload.get("trades"))
        wins = wins if wins is not None else inferred_wins
        losses = losses if losses is not None else inferred_losses
    _append_metric(metrics, "winning_trades", wins, "count")
    _append_metric(metrics, "losing_trades", losses, "count")
    if wins is not None and total_trades is not None and total_trades > 0:
        _append_metric(metrics, "win_rate", (wins / total_trades).quantize(Decimal("0.0001")), "ratio")

    _append_metric(
        metrics,
        "profit_total_ratio",
        _first_decimal(strategy_payload, "profit_total", "profit_total_ratio"),
        "ratio",
    )
    _append_metric(
        metrics,
        "profit_total_abs",
        _first_decimal(strategy_payload, "profit_total_abs", "total_profit_abs"),
        "quote_currency",
    )
    _append_metric(
        metrics,
        "max_drawdown_abs",
        _first_decimal(strategy_payload, "max_drawdown_abs", "max_drawdown"),
        "quote_currency",
    )
    _append_metric(
        metrics,
        "max_drawdown_ratio",
        _first_decimal(strategy_payload, "max_drawdown_account", "max_drawdown_ratio"),
        "ratio",
    )
    return metrics


def _wins_losses_from_trades(value: Any) -> tuple[Optional[Decimal], Optional[Decimal]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return None, None
    wins = Decimal("0")
    losses = Decimal("0")
    for trade in value:
        if not isinstance(trade, Mapping):
            continue
        profit = _first_decimal(trade, "profit_ratio", "profit_abs")
        if profit is None:
            continue
        if profit > 0:
            wins += 1
        elif profit < 0:
            losses += 1
    return wins, losses


def _first_decimal(payload: Mapping[str, Any], *keys: str) -> Optional[Decimal]:
    for key in keys:
        value = _decimal_from_any(payload.get(key))
        if value is not None:
            return value
    return None


def _append_metric(metrics: list[BacktestMetric], name: str, value: Optional[Decimal], unit: str) -> None:
    if value is not None:
        metrics.append(BacktestMetric(name=name, value=value, unit=unit))


def _decimal_from_any(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal_to_text(value: Decimal) -> str:
    if value == value.to_integral_value():
        return str(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return format(value.normalize(), "f")


def _optional_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(value)


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _stable_json_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _safe_slug(value: str) -> str:
    cleaned = [char.lower() if char.isalnum() else "_" for char in value]
    return "".join(cleaned).strip("_") or "artifact"
