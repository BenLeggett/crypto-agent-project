from __future__ import annotations

import os
from typing import Any

import requests
from dotenv import load_dotenv


class LocalLLMUnavailable(Exception):
    """Raised when the local LLM endpoint cannot be used."""


def _build_url(base_url: str, path: str) -> str:
    """Join a base URL and API path without duplicating slashes."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def ping(base_url: str, timeout: int = 2) -> bool:
    """Check whether the local LLM server responds to the models endpoint."""
    try:
        response = requests.get(_build_url(base_url, "/models"), timeout=timeout)
    except requests.RequestException:
        return False
    return response.status_code == 200


def complete(
    prompt: str,
    model: str,
    base_url: str,
    max_tokens: int = 1024,
    temperature: float = 0.2,
) -> str:
    """Send a chat completion request to the local LLM server."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    try:
        response = requests.post(
            _build_url(base_url, "/chat/completions"),
            json=payload,
            timeout=30,
        )
    except requests.RequestException as exc:
        raise LocalLLMUnavailable("Local LLM connection failed.") from exc

    if response.status_code != 200:
        raise ValueError(f"Unexpected status code from local LLM: {response.status_code}")

    try:
        data: dict[str, Any] = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("Malformed response from local LLM.") from exc

    if not isinstance(content, str):
        raise ValueError("Malformed response from local LLM.")
    return content


if __name__ == "__main__":
    load_dotenv()
    base_url = os.getenv("LOCAL_LLM_BASE_URL", "http://localhost:1234/v1")
    model = os.getenv("LOCAL_LLM_LOW_MODEL")
    reachable = ping(base_url)
    print(reachable)
    if not reachable:
        print("LM Studio not reachable")
        raise SystemExit(1)
    if not model:
        raise SystemExit("LOCAL_LLM_LOW_MODEL is not set")
    print(complete("Say hello in one sentence.", model, base_url))
