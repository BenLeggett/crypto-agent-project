"""Layered project configuration loader.

The loader intentionally supports only the simple YAML subset used by the
checked-in config files. A broader parser can be introduced when the config
surface grows enough to need it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Optional, Union

from libs.config.models import (
    AIConfig,
    AppConfig,
    AppMode,
    ConfigError,
    LoggingConfig,
    ProjectConfig,
    RiskConfig,
    SymbolsConfig,
)
from libs.config.validators import validate_config

CONFIG_FILES = ("app", "symbols", "risk", "logging", "ai")


def load_config(
    config_root: Union[str, Path] = "configs",
    env_name: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> ProjectConfig:
    """Load base config, overlay environment config, apply env vars, and validate."""
    env = os.environ if environ is None else environ
    selected_env = env_name or env.get("CONFIG_ENV") or "dry_run"
    root = Path(config_root)

    raw: dict[str, dict[str, Any]] = {}
    for section in CONFIG_FILES:
        raw[section] = _read_section(root / "base" / f"{section}.yaml")

    env_dir = root / selected_env
    if not env_dir.is_dir():
        raise ConfigError(f"Config environment directory does not exist: {env_dir}")

    for section in CONFIG_FILES:
        override_path = env_dir / f"{section}.yaml"
        if override_path.exists():
            raw[section] = _merge_dicts(raw[section], _read_section(override_path))

    _apply_env_overrides(raw, env)
    config = _build_project_config(selected_env, raw)
    return validate_config(config, env)


def _build_project_config(config_env: str, raw: Mapping[str, Mapping[str, Any]]) -> ProjectConfig:
    app = raw["app"]
    symbols = raw["symbols"]
    risk = raw["risk"]
    logging = raw["logging"]
    ai = raw["ai"]

    return ProjectConfig(
        config_env=config_env,
        app=AppConfig(
            mode=_enum_value(AppMode, _required(app, "mode")),
            service_name=str(_required(app, "service_name")),
            run_id_prefix=str(_required(app, "run_id_prefix")),
            execution=str(app.get("execution", "offline")),
            live_execution_enabled=_bool(app.get("live_execution_enabled", False)),
            requires_promotion_marker=_bool(app.get("requires_promotion_marker", False)),
        ),
        symbols=SymbolsConfig(
            symbols=tuple(_list(symbols.get("symbols", []))),
            timeframes=tuple(_list(symbols.get("timeframes", []))),
        ),
        risk=RiskConfig(
            enabled=_bool(_required(risk, "enabled")),
            live_execution_enabled=_bool(risk.get("live_execution_enabled", False)),
        ),
        logging=LoggingConfig(
            level=str(_required(logging, "level")).upper(),
            format=str(_required(logging, "format")),
        ),
        ai=AIConfig(
            provider=str(_required(ai, "provider")),
            default_model_tier=str(_required(ai, "default_model_tier")),
            premium_enabled=_bool(_required(ai, "premium_enabled")),
        ),
    )


def _read_section(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"Missing config file: {path}")
    return _parse_simple_yaml(path.read_text(encoding="utf-8"), path)


def _parse_simple_yaml(content: str, path: Path) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ConfigError(f"Invalid config line in {path}:{line_number}")
        key, value = line.split(":", 1)
        key = key.strip()
        if not key:
            raise ConfigError(f"Empty config key in {path}:{line_number}")
        parsed[key] = _parse_scalar(value.strip())
    return parsed


def _parse_scalar(value: str) -> Any:
    if value == "":
        return ""
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if value == "[]":
        return []
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [_strip_quotes(part.strip()) for part in inner.split(",")]
    return _strip_quotes(value)


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _merge_dicts(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    merged.update(override)
    return merged


def _apply_env_overrides(raw: MutableMapping[str, dict[str, Any]], env: Mapping[str, str]) -> None:
    mapping = {
        "APP_MODE": ("app", "mode", str),
        "APP_SERVICE_NAME": ("app", "service_name", str),
        "RUN_ID_PREFIX": ("app", "run_id_prefix", str),
        "APP_EXECUTION": ("app", "execution", str),
        "LIVE_EXECUTION_ENABLED": ("app", "live_execution_enabled", _bool),
        "REQUIRES_PROMOTION_MARKER": ("app", "requires_promotion_marker", _bool),
        "SYMBOLS": ("symbols", "symbols", _csv),
        "TIMEFRAMES": ("symbols", "timeframes", _csv),
        "RISK_ENABLED": ("risk", "enabled", _bool),
        "RISK_LIVE_EXECUTION_ENABLED": ("risk", "live_execution_enabled", _bool),
        "LOG_LEVEL": ("logging", "level", str),
        "LOG_FORMAT": ("logging", "format", str),
        "AI_PROVIDER": ("ai", "provider", str),
        "AI_DEFAULT_MODEL_TIER": ("ai", "default_model_tier", str),
        "AI_PREMIUM_ENABLED": ("ai", "premium_enabled", _bool),
    }
    for env_name, (section, key, caster) in mapping.items():
        if env_name in env:
            raw[section][key] = caster(env[env_name])


def _required(values: Mapping[str, Any], key: str) -> Any:
    if key not in values:
        raise ConfigError(f"Missing required config key: {key}")
    return values[key]


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise ConfigError(f"Expected boolean value, got {value!r}")


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, tuple):
        return [str(item) for item in value]
    raise ConfigError(f"Expected list value, got {value!r}")


def _csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _enum_value(enum_type: Any, value: Any) -> AppMode:
    try:
        return enum_type(str(value))
    except ValueError as exc:
        raise ConfigError(f"Unsupported app mode: {value!r}") from exc
