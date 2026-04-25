from __future__ import annotations

import json
import logging

from apps.collector import main as collector_main
from libs.common.logging import configure_logging, get_logger
from libs.config import load_config


def test_structured_logging_includes_service_and_run_id(capsys) -> None:
    config = load_config(environ={})
    run_id = configure_logging(config, service_name="unit_test")

    get_logger("tests.logging").info("hello", extra={"event": "test_event"})

    line = capsys.readouterr().err.strip()
    payload = json.loads(line)
    assert payload["service_name"] == "unit_test"
    assert payload["run_id"] == run_id
    assert payload["event"] == "test_event"
    assert payload["message"] == "hello"


def test_configure_logging_replaces_handlers_without_duplicates() -> None:
    config = load_config(environ={})

    configure_logging(config, service_name="first")
    configure_logging(config, service_name="second")

    assert len(logging.getLogger().handlers) == 1


def test_plain_logging_still_includes_context(capsys) -> None:
    config = load_config(environ={"LOG_FORMAT": "plain"})
    run_id = configure_logging(config, service_name="plain_test")

    get_logger("tests.logging").warning("plain message")

    line = capsys.readouterr().err.strip()
    assert "service=plain_test" in line
    assert f"run_id={run_id}" in line
    assert "plain message" in line


def test_app_entrypoint_uses_shared_structured_logging(capsys) -> None:
    assert collector_main.main() == 0

    line = capsys.readouterr().err.strip()
    payload = json.loads(line)
    assert payload["service_name"] == "collector"
    assert payload["run_id"] == "local-local"
    assert payload["event"] == "placeholder_started"
