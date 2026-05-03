from __future__ import annotations

import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


def _load_local_env() -> None:
    """Load the orchestrator-local .env file when present."""
    load_dotenv(Path(__file__).with_name(".env"))


def _resolve_webhook_url(webhook_url: str | None) -> str:
    """Resolve the webhook URL from an explicit value or environment."""
    if webhook_url is not None:
        return webhook_url.strip()
    _load_local_env()
    return (os.getenv("DISCORD_WEBHOOK_URL") or "").strip()


def _deliver(message: str, webhook_url: str | None = None) -> str:
    """Send the message or fall back to mock mode."""
    resolved_webhook = _resolve_webhook_url(webhook_url)
    if not resolved_webhook:
        print(f"[DISCORD-MOCK] {message}")
        return "mock"

    try:
        response = requests.post(
            resolved_webhook,
            json={"content": message},
            timeout=10,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"[DISCORD-ERROR] {exc}", file=sys.stderr)
        return "error"
    return "delivered"


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
