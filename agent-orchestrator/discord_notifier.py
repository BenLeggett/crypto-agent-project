from __future__ import annotations

import os
import sys
import time
from pathlib import Path

try:
    import requests
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    requests = None

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:  # pragma: no cover - fallback for non-venv interpreters
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        _ = (args, kwargs)
        return False


def _load_local_env() -> None:
    """Load the orchestrator-local .env file when present."""
    load_dotenv(Path(__file__).with_name(".env"))


def _resolve_webhook_url(webhook_url: str | None) -> str:
    """Resolve the webhook URL from an explicit value or environment."""
    if webhook_url is not None:
        return webhook_url.strip()
    _load_local_env()
    return (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()


def _retry_attempts() -> int:
    """Return configured webhook attempts, including the first try."""
    return max(1, int(os.getenv("DISCORD_WEBHOOK_RETRY_ATTEMPTS", "3")))


def _retry_backoff_seconds(attempt_index: int) -> float:
    """Return simple bounded backoff for webhook retries."""
    base_seconds = float(os.getenv("DISCORD_WEBHOOK_RETRY_BACKOFF_SECONDS", "1"))
    return min(10.0, base_seconds * (2 ** attempt_index))


def _retry_after_seconds(response: object, attempt_index: int) -> float:
    """Honor Discord Retry-After when present, otherwise use local backoff."""
    headers = getattr(response, "headers", {}) or {}
    retry_after = headers.get("Retry-After") or headers.get("retry-after")
    if retry_after is None:
        return _retry_backoff_seconds(attempt_index)
    try:
        return max(0.0, float(retry_after))
    except (TypeError, ValueError):
        return _retry_backoff_seconds(attempt_index)


def _is_retryable_status(status_code: int) -> bool:
    """Retry transient Discord webhook responses only."""
    return status_code == 429 or status_code in {500, 502, 503, 504}


def _deliver(message: str, webhook_url: str | None = None) -> str:
    """Send the message or fall back to mock mode."""
    resolved_webhook = _resolve_webhook_url(webhook_url)
    if not resolved_webhook:
        print(f"[DISCORD-MOCK] {message}")
        return "mock"
    if requests is None:
        print("[DISCORD-ERROR] requests is not installed.", file=sys.stderr)
        return "error"

    attempts = _retry_attempts()
    last_error = ""
    for attempt_index in range(attempts):
        response_for_delay = None
        try:
            response = requests.post(
                resolved_webhook,
                json={"content": message},
                timeout=10,
            )
            response_for_delay = response
        except requests.RequestException as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            retryable = True
        else:
            status_code = int(getattr(response, "status_code", 0))
            if 200 <= status_code < 300:
                return "delivered"
            detail = getattr(response, "text", "").strip().replace("\n", " ")[:300]
            last_error = f"HTTP {status_code}: {detail or 'no response body'}"
            retryable = _is_retryable_status(status_code)

        is_last_attempt = attempt_index == attempts - 1
        if is_last_attempt or not retryable:
            break
        delay = (
            _retry_after_seconds(response_for_delay, attempt_index)
            if response_for_delay is not None
            else _retry_backoff_seconds(attempt_index)
        )
        time.sleep(delay)

    print(f"[DISCORD-ERROR] {last_error}", file=sys.stderr)
    return "error"


def notify(message: str, webhook_url: str | None = None) -> None:
    """Send a Discord webhook notification or print a mock message."""
    _deliver(message, webhook_url)


def format_status(
    phase: str,
    task_id: str | int,
    task_title: str,
    model_used: str,
    outcome: str,
    next_action: str,
) -> str:
    """Format a status message for Discord."""
    return (
        f"[ORCHESTRATOR] {phase} \u00b7 Task {task_id}: {task_title}\n"
        f"Status: {outcome}\n"
        f"Model used: {model_used}\n"
        f"Next: {next_action}"
    )


def format_approval_request(
    gate_type: str,
    ref: str,
    verdict: str,
    timeout_minutes: int,
) -> str:
    """Format an approval request for Discord."""
    return (
        f"[ORCHESTRATOR \u00b7 APPROVAL REQUIRED] {gate_type}\n"
        f"Verdict: {verdict}\n"
        f"Action required: reply `!approve {ref}` or `!reject {ref} <notes>`\n"
        f"Timeout: {timeout_minutes} minutes"
    )


if __name__ == "__main__":
    result = _deliver("[ORCHESTRATOR TEST] Discord notifier verification message.")
    if result == "delivered":
        print("Delivered")
    elif result == "mock":
        print("Mock mode")
