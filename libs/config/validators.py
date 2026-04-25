"""Fail-fast validation for typed project configuration."""

from __future__ import annotations

from typing import Mapping

from libs.config.models import AIConfig, AppConfig, AppMode, ConfigError, ProjectConfig

ALLOWED_CONFIG_ENVS = {"dry_run", "live"}
ALLOWED_EXECUTIONS = {"offline", "dry_run", "gated_live"}
ALLOWED_TRADING_FOUNDATIONS = {"freqtrade"}
ALLOWED_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
ALLOWED_LOG_FORMATS = {"structured", "plain"}
ALLOWED_MODEL_TIERS = {"cheap", "default", "premium"}
REAL_AI_PROVIDERS = {"openai"}


def validate_config(config: ProjectConfig, environ: Mapping[str, str]) -> ProjectConfig:
    if config.config_env not in ALLOWED_CONFIG_ENVS:
        raise ConfigError(f"Unsupported config environment: {config.config_env!r}")

    _validate_app(config.app)
    _validate_symbols(config.symbols.symbols, "symbols")
    _validate_symbols(config.symbols.timeframes, "timeframes")
    _validate_risk(config)
    _validate_logging(config.logging.level, config.logging.format)
    _validate_ai(config.ai, environ)
    return config


def _validate_app(app: AppConfig) -> None:
    if not app.service_name:
        raise ConfigError("app.service_name is required")
    if not app.run_id_prefix:
        raise ConfigError("app.run_id_prefix is required")
    if app.trading_foundation not in ALLOWED_TRADING_FOUNDATIONS:
        raise ConfigError(f"Unsupported trading foundation: {app.trading_foundation!r}")
    if app.execution not in ALLOWED_EXECUTIONS:
        raise ConfigError(f"Unsupported execution mode: {app.execution!r}")
    if app.mode == AppMode.LIVE:
        if app.live_execution_enabled:
            raise ConfigError("live execution is not approved in this config foundation slice")
        if not app.requires_promotion_marker:
            raise ConfigError("live mode must require a promotion marker")


def _validate_symbols(values: tuple[str, ...], field_name: str) -> None:
    for value in values:
        if not value or not isinstance(value, str):
            raise ConfigError(f"{field_name} must contain non-empty strings")


def _validate_risk(config: ProjectConfig) -> None:
    if not config.risk.enabled:
        raise ConfigError("deterministic risk governor must remain enabled")
    if config.risk.live_execution_enabled:
        raise ConfigError("risk.live_execution_enabled must remain false until live readiness gates exist")


def _validate_logging(level: str, log_format: str) -> None:
    if level not in ALLOWED_LOG_LEVELS:
        raise ConfigError(f"Unsupported log level: {level!r}")
    if log_format not in ALLOWED_LOG_FORMATS:
        raise ConfigError(f"Unsupported log format: {log_format!r}")


def _validate_ai(ai: AIConfig, environ: Mapping[str, str]) -> None:
    if not ai.provider:
        raise ConfigError("ai.provider is required")
    if ai.default_model_tier not in ALLOWED_MODEL_TIERS:
        raise ConfigError(f"Unsupported AI model tier: {ai.default_model_tier!r}")
    if ai.premium_enabled and ai.default_model_tier == "premium":
        raise ConfigError("premium models cannot be the default monitoring tier")
    if ai.provider in REAL_AI_PROVIDERS and not environ.get("OPENAI_API_KEY"):
        raise ConfigError("OPENAI_API_KEY is required when ai.provider is openai")
