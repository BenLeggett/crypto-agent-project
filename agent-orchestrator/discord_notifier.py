from __future__ import annotations


def notify(message: str, webhook_url: str | None = None) -> None:
    """Placeholder Discord notification sender."""
    _ = (message, webhook_url)


def format_status(status: str) -> str:
    """Return a placeholder status message."""
    return status


def format_approval_request(reference: str, summary: str) -> str:
    """Return a placeholder approval request message."""
    return f"{reference}: {summary}"
