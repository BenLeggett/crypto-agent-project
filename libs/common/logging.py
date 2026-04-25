"""Shared logging setup for app entrypoints."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any, Optional

from libs.config.models import ProjectConfig

RESERVED_LOG_RECORD_KEYS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
}


class StructuredJsonFormatter(logging.Formatter):
    """Format log records as compact JSON with service and run context."""

    def __init__(self, service_name: str, run_id: str) -> None:
        super().__init__()
        self.service_name = service_name
        self.run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "service_name": self.service_name,
            "run_id": self.run_id,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in RESERVED_LOG_RECORD_KEYS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, sort_keys=True, default=str)


class PlainContextFormatter(logging.Formatter):
    """Human-readable formatter that still includes service and run context."""

    def __init__(self, service_name: str, run_id: str) -> None:
        super().__init__("%(asctime)s %(levelname)s %(name)s service=%(service_name)s run_id=%(run_id)s %(message)s")
        self.service_name = service_name
        self.run_id = run_id

    def format(self, record: logging.LogRecord) -> str:
        record.service_name = self.service_name
        record.run_id = self.run_id
        return super().format(record)


def configure_logging(
    config: ProjectConfig,
    service_name: Optional[str] = None,
    run_id: Optional[str] = None,
) -> str:
    """Configure root logging and return the run ID applied to log records."""
    resolved_service_name = service_name or config.app.service_name
    resolved_run_id = run_id or f"{config.app.run_id_prefix}-local"
    handler = logging.StreamHandler(sys.stderr)

    if config.logging.format == "structured":
        handler.setFormatter(StructuredJsonFormatter(resolved_service_name, resolved_run_id))
    else:
        handler.setFormatter(PlainContextFormatter(resolved_service_name, resolved_run_id))

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(config.logging.level)
    return resolved_run_id


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
