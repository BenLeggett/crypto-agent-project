from __future__ import annotations

from pathlib import Path

import pytest

from libs.config import AppMode, ConfigError, load_config


def test_loads_dry_run_config_by_default() -> None:
    config = load_config(environ={})

    assert config.config_env == "dry_run"
    assert config.app.mode == AppMode.PAPER
    assert config.app.execution == "dry_run"
    assert config.app.live_execution_enabled is False
    assert config.risk.enabled is True
    assert config.risk.live_execution_enabled is False
    assert config.ai.provider == "mock"


def test_loads_live_config_as_gated_and_disabled() -> None:
    config = load_config(env_name="live", environ={})

    assert config.config_env == "live"
    assert config.app.mode == AppMode.LIVE
    assert config.app.execution == "gated_live"
    assert config.app.live_execution_enabled is False
    assert config.app.requires_promotion_marker is True


def test_environment_overrides_take_precedence() -> None:
    config = load_config(
        environ={
            "CONFIG_ENV": "dry_run",
            "SYMBOLS": "BTC/USDT, ETH/USDT",
            "TIMEFRAMES": "1h, 4h",
            "LOG_LEVEL": "debug",
            "AI_PROVIDER": "mock",
        }
    )

    assert config.symbols.symbols == ("BTC/USDT", "ETH/USDT")
    assert config.symbols.timeframes == ("1h", "4h")
    assert config.logging.level == "DEBUG"


def test_invalid_mode_fails_fast(tmp_path: Path) -> None:
    _write_minimal_config(tmp_path)
    (tmp_path / "dry_run" / "app.yaml").write_text(
        "mode: unsafe\nservice_name: test\nrun_id_prefix: local\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="Unsupported app mode"):
        load_config(config_root=tmp_path, environ={})


def test_live_execution_enabled_fails_closed(tmp_path: Path) -> None:
    _write_minimal_config(tmp_path)
    (tmp_path / "live" / "app.yaml").write_text(
        "mode: live\nexecution: gated_live\nlive_execution_enabled: true\nrequires_promotion_marker: true\n",
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match="live execution is not approved"):
        load_config(config_root=tmp_path, env_name="live", environ={})


def test_real_ai_provider_requires_secret() -> None:
    with pytest.raises(ConfigError, match="OPENAI_API_KEY"):
        load_config(environ={"AI_PROVIDER": "openai"})


def _write_minimal_config(root: Path) -> None:
    base = root / "base"
    dry_run = root / "dry_run"
    live = root / "live"
    base.mkdir(parents=True)
    dry_run.mkdir()
    live.mkdir()
    (base / "app.yaml").write_text(
        "mode: paper\nservice_name: test\nrun_id_prefix: local\n",
        encoding="utf-8",
    )
    (base / "symbols.yaml").write_text("symbols: []\ntimeframes: []\n", encoding="utf-8")
    (base / "risk.yaml").write_text(
        "enabled: true\nlive_execution_enabled: false\n",
        encoding="utf-8",
    )
    (base / "logging.yaml").write_text("level: INFO\nformat: structured\n", encoding="utf-8")
    (base / "ai.yaml").write_text(
        "provider: mock\ndefault_model_tier: cheap\npremium_enabled: false\n",
        encoding="utf-8",
    )
    (dry_run / "app.yaml").write_text("mode: paper\nexecution: dry_run\n", encoding="utf-8")
    (live / "app.yaml").write_text(
        "mode: live\nexecution: gated_live\nlive_execution_enabled: false\nrequires_promotion_marker: true\n",
        encoding="utf-8",
    )
