"""Freqtrade adapter for the shared deterministic regime/breakout strategy.

This module is intentionally thin. Freqtrade owns runtime candle delivery and
later order lifecycle behavior, while the project-owned deterministic strategy
and decisioning modules remain the source of truth for signals and proposals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Optional, Sequence

try:  # pragma: no cover - exercised only when Freqtrade is installed.
    from freqtrade.strategy import IStrategy
except Exception:  # pragma: no cover - local tests run without Freqtrade.

    class IStrategy:  # type: ignore[no-redef]
        """Import-safe shim so shared adapter helpers can be tested locally."""


from libs.decisioning.deterministic_rules import DeterministicDecisionResult, DeterministicProposalConfig
from libs.decisioning.schemas import DecisionMode, TradeProposal
from libs.strategy.interfaces import Candle, MarketSeries, StrategyContext, TradeSide
from libs.strategy.signal_snapshot import SignalSnapshotSizingConfig, build_signal_snapshot


@dataclass(frozen=True)
class RegimeBreakoutAdapterConfig:
    """Local adapter settings that do not require exchange secrets."""

    allowed_symbols: tuple[str, ...]
    timeframe: str = "4h"
    run_id: str = "freqtrade-adapter"
    config_hash: str = "freqtrade-adapter-local"
    equity: Decimal = Decimal("10000")
    risk_fraction: Decimal = Decimal("0.01")
    max_position_value: Decimal = Decimal("1000")
    proposal_ttl_ms: int = 300_000
    enable_freqtrade_entries: bool = False

    def __post_init__(self) -> None:
        if not self.allowed_symbols:
            raise ValueError("allowed_symbols must not be empty")
        if not self.timeframe.strip():
            raise ValueError("timeframe must be non-empty")


class RegimeBreakoutStrategy(IStrategy):
    """Freqtrade hook surface backed by shared strategy and proposal logic."""

    timeframe = "4h"
    startup_candle_count = 40
    process_only_new_candles = True
    can_short = False
    minimal_roi = {"0": 100}
    stoploss = -0.99

    adapter_config = RegimeBreakoutAdapterConfig(allowed_symbols=("BTC/USDT",))

    def populate_indicators(self, dataframe: Any, metadata: Mapping[str, Any]) -> Any:
        """Attach the latest shared strategy decision to the candle frame."""

        return self._annotate_latest_decision(dataframe, metadata)

    def populate_entry_trend(self, dataframe: Any, metadata: Mapping[str, Any]) -> Any:
        """Populate conservative entry columns from a validated proposal record.

        Entries are disabled by default until the later supervisor/risk wiring
        phase can approve intents before Freqtrade dry-run/live execution.
        """

        annotated = self._annotate_latest_decision(dataframe, metadata)
        _ensure_column(annotated, "enter_long", 0)
        _ensure_column(annotated, "enter_short", 0)
        _ensure_column(annotated, "enter_tag", "")

        if not self.adapter_config.enable_freqtrade_entries:
            return annotated

        result = latest_decision_from_dataframe(annotated)
        if not isinstance(result.output, TradeProposal):
            return annotated
        last_index = _last_index(annotated)
        if last_index is None:
            return annotated

        if result.output.side is TradeSide.LONG:
            _set_cell(annotated, last_index, "enter_long", 1)
        elif result.output.side is TradeSide.SHORT and self.can_short:
            _set_cell(annotated, last_index, "enter_short", 1)
        _set_cell(annotated, last_index, "enter_tag", "shared_deterministic_proposal")
        return annotated

    def populate_exit_trend(self, dataframe: Any, metadata: Mapping[str, Any]) -> Any:
        """Leave exit placement to Freqtrade/runtime controls for this task."""

        _ensure_column(dataframe, "exit_long", 0)
        _ensure_column(dataframe, "exit_short", 0)
        return dataframe

    def _annotate_latest_decision(self, dataframe: Any, metadata: Mapping[str, Any]) -> Any:
        result = latest_decision_from_dataframe(
            dataframe,
            pair=str(metadata.get("pair", "")),
            adapter_config=self.adapter_config,
        )
        last_index = _last_index(dataframe)
        if last_index is None:
            return dataframe

        output = result.output
        output_record = output.to_record()
        _set_cell(dataframe, last_index, "ca_decision_record", result.to_record())
        _set_cell(dataframe, last_index, "ca_decision_kind", "proposal" if isinstance(output, TradeProposal) else "no_trade")
        _set_cell(dataframe, last_index, "ca_symbol", result.decision_input.market.symbol)
        _set_cell(dataframe, last_index, "ca_requires_supervisor_review", isinstance(output, TradeProposal))
        _set_cell(dataframe, last_index, "ca_proposal_id", output_record.get("proposal_id", ""))
        _set_cell(dataframe, last_index, "ca_no_trade_reason", output_record.get("reason", ""))
        return dataframe


def latest_decision_from_dataframe(
    dataframe: Any,
    *,
    pair: Optional[str] = None,
    adapter_config: Optional[RegimeBreakoutAdapterConfig] = None,
) -> DeterministicDecisionResult:
    """Build the latest shared deterministic decision from Freqtrade candles."""

    config = adapter_config or RegimeBreakoutStrategy.adapter_config
    symbol = pair or _pair_from_config(config)
    records = _records_from_dataframe(dataframe)
    series = market_series_from_records(symbol=symbol, timeframe=config.timeframe, records=records)
    context = StrategyContext(
        run_id=config.run_id,
        config_hash=config.config_hash,
        as_of_ms=series.candles[-1].timestamp_ms,
        metadata={"adapter": "freqtrade"},
    )
    snapshot = build_signal_snapshot(
        series,
        context,
        sizing_config=SignalSnapshotSizingConfig(
            equity=config.equity,
            risk_fraction=config.risk_fraction,
            max_position_value=config.max_position_value,
        ),
    )
    decision_config = DeterministicProposalConfig(
        allowed_symbols=config.allowed_symbols,
        mode=DecisionMode.PAPER,
        proposal_ttl_ms=config.proposal_ttl_ms,
    )
    from libs.decisioning.deterministic_rules import build_deterministic_decision

    return build_deterministic_decision(snapshot, config=decision_config)


def market_series_from_records(
    *,
    symbol: str,
    timeframe: str,
    records: Sequence[Mapping[str, Any]],
) -> MarketSeries:
    """Convert Freqtrade-style OHLCV rows into the shared strategy contract."""

    if not records:
        raise ValueError("records must not be empty")
    candles = tuple(_candle_from_record(symbol, timeframe, record) for record in records)
    return MarketSeries(symbol=symbol, timeframe=timeframe, candles=candles)


def _candle_from_record(symbol: str, timeframe: str, record: Mapping[str, Any]) -> Candle:
    timestamp_value = record.get("date", record.get("timestamp", record.get("timestamp_ms")))
    if timestamp_value is None:
        raise ValueError("record must include date, timestamp, or timestamp_ms")
    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        timestamp_ms=_timestamp_ms(timestamp_value),
        open=_decimal(record["open"], "open"),
        high=_decimal(record["high"], "high"),
        low=_decimal(record["low"], "low"),
        close=_decimal(record["close"], "close"),
        volume=_decimal(record.get("volume", "0"), "volume"),
    )


def _records_from_dataframe(dataframe: Any) -> tuple[Mapping[str, Any], ...]:
    if hasattr(dataframe, "to_dict"):
        records = dataframe.to_dict("records")
        return tuple(records)
    if isinstance(dataframe, Sequence):
        return tuple(dataframe)  # type: ignore[arg-type]
    raise TypeError("dataframe must be a pandas-like frame or a sequence of row mappings")


def _timestamp_ms(value: Any) -> int:
    if isinstance(value, datetime):
        timestamp = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return int(timestamp.timestamp() * 1000)
    if hasattr(value, "timestamp"):
        return int(value.timestamp() * 1000)
    if isinstance(value, str):
        normalized = value.replace("Z", "+00:00")
        return _timestamp_ms(datetime.fromisoformat(normalized))
    if isinstance(value, (int, float)):
        numeric = int(value)
        return numeric if numeric > 10_000_000_000 else numeric * 1000
    raise TypeError("timestamp value must be datetime, ISO string, seconds, or milliseconds")


def _decimal(value: Any, field_name: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field_name} must be Decimal-compatible") from exc
    if not parsed.is_finite():
        raise ValueError(f"{field_name} must be finite")
    return parsed


def _pair_from_config(config: RegimeBreakoutAdapterConfig) -> str:
    if len(config.allowed_symbols) != 1:
        raise ValueError("pair metadata is required when multiple allowed symbols are configured")
    return config.allowed_symbols[0]


def _last_index(dataframe: Any) -> Any:
    if hasattr(dataframe, "index"):
        if len(dataframe.index) == 0:
            return None
        return dataframe.index[-1]
    if isinstance(dataframe, Sequence):
        return len(dataframe) - 1 if dataframe else None
    return None


def _ensure_column(dataframe: Any, column: str, default: Any) -> None:
    if hasattr(dataframe, "columns") and column not in dataframe.columns:
        dataframe[column] = default


def _set_cell(dataframe: Any, index: Any, column: str, value: Any) -> None:
    if hasattr(dataframe, "columns") and column not in dataframe.columns:
        dataframe[column] = [None] * len(dataframe)
    if hasattr(dataframe, "at"):
        dataframe.at[index, column] = value
        return
    if hasattr(dataframe, "loc"):
        dataframe.loc[index, column] = value
        return
    dataframe[index][column] = value


__all__ = [
    "RegimeBreakoutAdapterConfig",
    "RegimeBreakoutStrategy",
    "latest_decision_from_dataframe",
    "market_series_from_records",
]
