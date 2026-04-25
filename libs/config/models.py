"""Typed configuration models for local, paper, and future live modes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple


class ConfigError(ValueError):
    """Raised when configuration is missing, malformed, or unsafe."""


class AppMode(str, Enum):
    OFFLINE = "offline"
    PAPER = "paper"
    LIVE = "live"


@dataclass(frozen=True)
class AppConfig:
    mode: AppMode
    service_name: str
    run_id_prefix: str
    trading_foundation: str
    execution: str
    live_execution_enabled: bool
    requires_promotion_marker: bool


@dataclass(frozen=True)
class SymbolsConfig:
    symbols: Tuple[str, ...]
    timeframes: Tuple[str, ...]


@dataclass(frozen=True)
class RiskConfig:
    enabled: bool
    live_execution_enabled: bool


@dataclass(frozen=True)
class LoggingConfig:
    level: str
    format: str


@dataclass(frozen=True)
class AIConfig:
    provider: str
    default_model_tier: str
    premium_enabled: bool


@dataclass(frozen=True)
class ProjectConfig:
    config_env: str
    app: AppConfig
    symbols: SymbolsConfig
    risk: RiskConfig
    logging: LoggingConfig
    ai: AIConfig
