from __future__ import annotations

import os

import local_llm_client


def _required_config(config: dict, key: str) -> str:
    """Return a required config value for local review."""
    value = config.get(key)
    if value is None or str(value).strip() == "":
        raise local_llm_client.LocalLLMUnavailable(f"{key} is not set.")
    return str(value)


def _float_config(config: dict, key: str, default: float) -> float:
    value = config.get(key)
    if value is None or str(value).strip() == "":
        return default
    return float(value)


def _int_config(config: dict, key: str, default: int) -> int:
    value = config.get(key)
    if value is None or str(value).strip() == "":
        return default
    return int(value)


def _bool_config(config: dict, key: str, default: bool = False) -> bool:
    value = config.get(key)
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _optional_config(config: dict, key: str, default: str | None = None) -> str | None:
    value = config.get(key)
    if value is None or str(value).strip() == "":
        return default
    return str(value)


def _review_prompt(failure_context: str, depth: str = "medium") -> str:
    """Build the bounded medium-model review prompt."""
    if depth == "low":
        return (
            "You are a fast local diagnostic reviewer for a deterministic development orchestrator.\n"
            "Your response is advisory only. Deterministic validator output is authoritative. "
            "Do not suggest live trading, wallet wiring, or bypassing validation, risk gates, journals, "
            "or promotion criteria.\n\n"
            "Use only the compact failure context below. Return no more than 5 short bullets covering "
            "probable cause, likely file area, and next debugging step.\n\n"
            "Failure context:\n"
            f"{failure_context}"
        )
    return (
        "You are a local diagnostic reviewer for a deterministic development orchestrator.\n"
        "Your response is advisory only. Do not claim validation passed. Do not suggest live trading, "
        "live wallet wiring, or bypassing deterministic validation, risk gates, approval gates, journals, "
        "or promotion criteria.\n\n"
        "Use only the compact failure context below. Do not infer hidden repository state.\n\n"
        "Return exactly these sections:\n"
        "1. Probable cause\n"
        "2. Likely files involved\n"
        "3. Safest next debugging step\n"
        "4. Human review needed: yes/no with one reason\n\n"
        "Failure context:\n"
        f"{failure_context}"
    )


def review_validation_failure_with_low_model(
    failure_context: str,
    config: dict,
) -> dict[str, object]:
    """Invoke the low local model for fast advisory validation failure review."""
    base_url = _required_config(config, "LOCAL_LLM_BASE_URL")
    model = _required_config(config, "LOCAL_LLM_LOW_MODEL")
    review_timeout = _float_config(config, "LOCAL_LLM_LOW_TIMEOUT_SECONDS", 30)
    max_tokens = _int_config(config, "LOCAL_LLM_LOW_MAX_TOKENS", 256)
    keep_alive = _optional_config(config, "LOCAL_LLM_LOW_KEEP_ALIVE", "30m")

    try:
        summary = local_llm_client.complete(
            _review_prompt(failure_context, depth="low"),
            model,
            base_url,
            timeout=review_timeout,
            max_tokens=max_tokens,
            temperature=0.2,
            keep_alive=keep_alive,
        )
        summary = summary.strip()
    except Exception as exc:
        return {
            "review_available": False,
            "model_used": "none",
            "summary": f"Low local diagnosis unavailable: {type(exc).__name__}: {exc}",
            "fallback_recommended": True,
        }

    if not summary:
        return {
            "review_available": False,
            "model_used": "none",
            "summary": "Low local diagnosis returned an empty response.",
            "fallback_recommended": True,
        }

    return {
        "review_available": True,
        "model_used": model,
        "summary": summary,
        "fallback_recommended": False,
    }


def review_validation_failure_with_medium_model(
    failure_context: str,
    config: dict,
) -> dict[str, object]:
    """Warm and invoke the medium local model for advisory validation failure review."""
    base_url = _required_config(config, "LOCAL_LLM_BASE_URL")
    model = _required_config(config, "LOCAL_LLM_MEDIUM_MODEL")
    warmup_timeout = _float_config(config, "LOCAL_LLM_MEDIUM_WARMUP_TIMEOUT_SECONDS", 120)
    review_timeout = _float_config(config, "LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS", 180)
    max_tokens = _int_config(config, "LOCAL_LLM_MEDIUM_MAX_TOKENS", 600)
    keep_alive = _optional_config(config, "LOCAL_LLM_MEDIUM_KEEP_ALIVE", "60m")
    unload_after_review = _bool_config(config, "LOCAL_LLM_UNLOAD_MEDIUM_AFTER_REVIEW", False)

    warmup_ok = local_llm_client.warmup_model(
        model,
        base_url,
        timeout=warmup_timeout,
        keep_alive=keep_alive,
    )
    if not warmup_ok:
        return {
            "review_available": False,
            "model_used": "none",
            "summary": "Medium local model unavailable or timed out during warmup.",
            "fallback_recommended": True,
        }

    try:
        summary = local_llm_client.complete(
            _review_prompt(failure_context),
            model,
            base_url,
            timeout=review_timeout,
            max_tokens=max_tokens,
            temperature=0.2,
            keep_alive=keep_alive,
        )
        summary = summary.strip()
    except Exception as exc:
        return {
            "review_available": False,
            "model_used": "none",
            "summary": f"Medium local review unavailable: {type(exc).__name__}: {exc}",
            "fallback_recommended": True,
        }
    finally:
        if unload_after_review:
            local_llm_client.unload_model(
                model,
                base_url,
                timeout=float(os.getenv("LOCAL_LLM_UNLOAD_TIMEOUT_SECONDS", "10")),
            )

    if not summary:
        return {
            "review_available": False,
            "model_used": "none",
            "summary": "Medium local review returned an empty response.",
            "fallback_recommended": True,
        }

    return {
        "review_available": True,
        "model_used": model,
        "summary": summary,
        "fallback_recommended": False,
    }
