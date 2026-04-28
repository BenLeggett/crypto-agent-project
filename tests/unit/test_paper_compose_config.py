from __future__ import annotations

from pathlib import Path


def test_paper_compose_starts_expected_mock_safe_services() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    for service_name in [
        "paper-audit-bootstrap:",
        "decision-engine:",
        "supervisor:",
        "freqtrade-dryrun:",
    ]:
        assert service_name in compose
    assert "scripts/bootstrap_paper_runtime.py" in compose
    assert "apps.decision_engine.main" in compose
    assert "apps.supervisor.main" in compose
    assert "freqtradeorg/freqtrade:stable" in compose
    assert "freqtrade/user_data/config.dryrun.json" in compose


def test_paper_compose_keeps_live_execution_and_secrets_unwired() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")

    assert "config.live.json" not in compose
    assert "LIVE_EXECUTION_ENABLED: \"false\"" in compose
    assert "RISK_LIVE_EXECUTION_ENABLED: \"false\"" in compose
    assert "AI_PROVIDER: mock" in compose
    assert "EXCHANGE_API_KEY" not in compose
    assert "EXCHANGE_API_SECRET" not in compose
    assert "OPERATOR_UPDATE_WEBHOOK_URL" not in compose


def test_makefile_exposes_paper_stack_commands() -> None:
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "paper-up:" in makefile
    assert "docker compose up" in makefile
    assert "paper-down:" in makefile
    assert "paper-replay:" in makefile
