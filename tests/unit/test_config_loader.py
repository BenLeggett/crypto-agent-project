from __future__ import annotations

from pathlib import Path
from shutil import copytree

import pytest

from libs.config import AppMode, ConfigError, load_config

FIXTURE_ROOT = Path("tests/fixtures/configs/valid")


def test_loads_dry_run_config_by_default() -> None:
    config = load_config(config_root=FIXTURE_ROOT, environ={})

    assert config.config_env == "dry_run"
    assert config.app.mode == AppMode.PAPER
    assert config.app.service_name == "fixture-agent"
    assert config.app.execution == "dry_run"
    assert config.app.live_execution_enabled is False
    assert config.symbols.symbols == ("BTC/USDT", "ETH/USDT")
    assert config.symbols.timeframes == ("1h", "4h")
    assert config.risk.enabled is True
    assert config.risk.live_execution_enabled is False
    assert config.ai.provider == "mock"


def test_loads_live_config_as_gated_and_disabled() -> None:
    config = load_config(config_root=FIXTURE_ROOT, env_name="live", environ={})

    assert config.config_env == "live"
    assert config.app.mode == AppMode.LIVE
    assert config.app.execution == "gated_live"
    assert config.app.live_execution_enabled is False
    assert config.app.requires_promotion_marker is True


def test_environment_overrides_take_precedence() -> None:
    config = load_config(
        config_root=FIXTURE_ROOT,
        environ={
            "CONFIG_ENV": "dry_run",
            "SYMBOLS": "SOL/USDT, AVAX/USDT",
            "TIMEFRAMES": "15m, 1h",
            "LOG_LEVEL": "debug",
            "APP_SERVICE_NAME": "override-agent",
            "AI_PROVIDER": "mock",
        }
    )

    assert config.app.service_name == "override-agent"
    assert config.symbols.symbols == ("SOL/USDT", "AVAX/USDT")
    assert config.symbols.timeframes == ("15m", "1h")
    assert config.logging.level == "DEBUG"


def test_explicit_env_name_wins_over_config_env_override() -> None:
    config = load_config(
        config_root=FIXTURE_ROOT,
        env_name="live",
        environ={"CONFIG_ENV": "dry_run"},
    )

    assert config.config_env == "live"
    assert config.app.mode == AppMode.LIVE


def test_invalid_mode_fails_fast(tmp_path: Path) -> None:
    config_root = _copy_fixture(tmp_path)
    (tmp_path / "dry_run" / "app.yaml").write_text(
        "mode: unsafe\nservice_name: test\nrun_id_prefix: local\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Unsupported app mode"):
        load_config(config_root=config_root, environ={})


def test_missing_required_field_fails_fast(tmp_path: Path) -> None:
    config_root = _copy_fixture(tmp_path)
    (tmp_path / "base" / "app.yaml").write_text(
        "mode: paper\nrun_id_prefix: local\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="service_name"):
        load_config(config_root=config_root, environ={})


@pytest.mark.parametrize(
    ("env", "match"),
    [
        ({"APP_EXECUTION": "live_now"}, "Unsupported execution mode"),
        ({"LOG_LEVEL": "TRACE"}, "Unsupported log level"),
        ({"LOG_FORMAT": "rainbow"}, "Unsupported log format"),
        ({"AI_DEFAULT_MODEL_TIER": "expensive"}, "Unsupported AI model tier"),
    ],
)
def test_enum_bounds_fail_fast(env: dict[str, str], match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        load_config(config_root=FIXTURE_ROOT, environ=env)


def test_unknown_config_environment_fails_fast() -> None:
    with pytest.raises(ConfigError, match="Config environment directory does not exist"):
        load_config(config_root=FIXTURE_ROOT, env_name="prod", environ={})


def test_live_execution_enabled_fails_closed(tmp_path: Path) -> None:
    config_root = _copy_fixture(tmp_path)
    (tmp_path / "live" / "app.yaml").write_text(
        "mode: live\nexecution: gated_live\nlive_execution_enabled: true\nrequires_promotion_marker: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="live execution is not approved"):
        load_config(config_root=config_root, env_name="live", environ={})


def test_live_mode_requires_promotion_marker(tmp_path: Path) -> None:
    config_root = _copy_fixture(tmp_path)
    (tmp_path / "live" / "app.yaml").write_text(
        "mode: live\nexecution: gated_live\nlive_execution_enabled: false\nrequires_promotion_marker: false\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="live mode must require a promotion marker"):
        load_config(config_root=config_root, env_name="live", environ={})


def test_risk_governor_cannot_be_disabled() -> None:
    with pytest.raises(ConfigError, match="deterministic risk governor"):
        load_config(config_root=FIXTURE_ROOT, environ={"RISK_ENABLED": "false"})


def test_risk_live_execution_flag_fails_closed() -> None:
    with pytest.raises(ConfigError, match="risk.live_execution_enabled"):
        load_config(config_root=FIXTURE_ROOT, environ={"RISK_LIVE_EXECUTION_ENABLED": "true"})


def test_premium_model_cannot_be_default_monitoring_tier() -> None:
    with pytest.raises(ConfigError, match="premium models cannot be the default"):
        load_config(
            config_root=FIXTURE_ROOT,
            environ={"AI_DEFAULT_MODEL_TIER": "premium", "AI_PREMIUM_ENABLED": "true"},
        )


def test_real_ai_provider_requires_secret() -> None:
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_config(config_root=FIXTURE_ROOT, environ={"AI_PROVIDER": "openai"})


def test_real_ai_provider_loads_when_secret_is_present() -> None:
    config = load_config(
        config_root=FIXTURE_ROOT,
        environ={"AI_PROVIDER": "openai", "OPENAI_API_KEY": "test-placeholder"},
    )

    assert config.ai.provider == "openai"


def _copy_fixture(tmp_path: Path) -> Path:
    copytree(FIXTURE_ROOT, tmp_path, dirs_exist_ok=True)
    return tmp_path
