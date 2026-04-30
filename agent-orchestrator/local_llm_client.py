from __future__ import annotations


class LocalLLMUnavailable(RuntimeError):
    """Raised when the local LLM endpoint cannot be used."""


def ping(base_url: str, timeout_seconds: float = 2.0) -> bool:
    """Placeholder health check for the local LLM server."""
    _ = (base_url, timeout_seconds)
    return False


def complete(
    prompt: str,
    model: str,
    base_url: str,
    api_key: str | None = None,
) -> str:
    """Placeholder local completion call."""
    _ = (prompt, model, base_url, api_key)
    return ""
