from __future__ import annotations

import os
import time
from typing import Any

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


class LocalLLMUnavailable(Exception):
    """Raised when the local LLM endpoint cannot be used."""


def _build_url(base_url: str, path: str) -> str:
    """Join a base URL and API path without duplicating slashes."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def ping(base_url: str, timeout: int = 2) -> bool:
    """Check whether the local LLM server responds to the models endpoint."""
    if requests is None:
        return False
    try:
        response = requests.get(_build_url(base_url, "/models"), timeout=timeout)
    except requests.RequestException:
        return False
    return response.status_code == 200


def _retry_attempts() -> int:
    """Return configured local LLM attempts, including the first try."""
    return max(1, int(os.getenv("LOCAL_LLM_RETRY_ATTEMPTS", "2")))


def _retry_delay_seconds(attempt_index: int) -> float:
    """Return a small retry delay for local model startup hiccups."""
    base_seconds = float(os.getenv("LOCAL_LLM_RETRY_BACKOFF_SECONDS", "1"))
    return min(5.0, base_seconds * (attempt_index + 1))


def _is_retryable_status(status_code: int) -> bool:
    """Retry transient local server failures only."""
    return status_code == 429 or status_code in {500, 502, 503, 504}


def _base_api_url(base_url: str) -> str:
    """Return the Ollama-compatible root URL for non-/v1 lifecycle calls."""
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        return normalized.removesuffix("/v1")
    return normalized


def complete(
    prompt: str,
    model: str,
    base_url: str,
    max_tokens: int = 600,
    temperature: float = 0.2,
    timeout: float | None = None,
    keep_alive: str | int | None = None,
) -> str:
    """Send a chat completion request to the local LLM server."""
    if requests is None:
        raise LocalLLMUnavailable("requests is not installed.")

    request_timeout = timeout
    if request_timeout is None:
        request_timeout = float(os.getenv("LOCAL_LLM_TIMEOUT_SECONDS", "45"))

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if keep_alive is not None and str(keep_alive).strip() != "":
        payload["keep_alive"] = keep_alive
    attempts = _retry_attempts()
    response = None
    last_connection_error = ""
    for attempt_index in range(attempts):
        try:
            response = requests.post(
                _build_url(base_url, "/chat/completions"),
                json=payload,
                timeout=request_timeout,
            )
        except requests.RequestException as exc:
            last_connection_error = f"{type(exc).__name__}: {exc}"
            if attempt_index < attempts - 1:
                time.sleep(_retry_delay_seconds(attempt_index))
                continue
            raise LocalLLMUnavailable(
                f"Local LLM connection failed with request_timeout = {request_timeout} "
                f"for {base_url} with model {model}: {last_connection_error}"
            ) from exc

        if response.status_code == 200:
            break
        if _is_retryable_status(response.status_code) and attempt_index < attempts - 1:
            time.sleep(_retry_delay_seconds(attempt_index))
            continue
        break

    if response is None:
        raise LocalLLMUnavailable(
            f"Local LLM connection failed for {base_url} with model {model}: {last_connection_error}"
        )

    if response.status_code != 200:
        detail = response.text.strip().replace("\n", " ")[:300]
        raise ValueError(
            f"Unexpected status code from local LLM: {response.status_code}; "
            f"model={model}; detail={detail or 'no response body'}"
        )

    try:
        data: dict[str, Any] = response.json()
        content = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ValueError("Malformed response from local LLM.") from exc

    if not isinstance(content, str):
        raise ValueError("Malformed response from local LLM.")
    return content


def warmup_model(
    model: str,
    base_url: str,
    timeout: float,
    strict: bool = False,
    keep_alive: str | int | None = None,
) -> bool:
    """Warm a local model with a tiny request before a heavier review."""
    try:
        content = complete(
            "Reply with exactly: ready",
            model,
            base_url,
            max_tokens=8,
            temperature=0.0,
            timeout=timeout,
            keep_alive=keep_alive,
        )
    except Exception:
        if strict:
            raise
        return False
    return bool(content.strip())


def unload_model(model: str, base_url: str, timeout: float = 10) -> bool:
    """Best-effort Ollama model unload; disabled by callers by default."""
    if requests is None:
        return False
    payload = {"model": model, "prompt": "", "keep_alive": 0}
    try:
        response = requests.post(
            _build_url(_base_api_url(base_url), "/api/generate"),
            json=payload,
            timeout=timeout,
        )
    except requests.RequestException:
        return False
    return 200 <= response.status_code < 300


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
