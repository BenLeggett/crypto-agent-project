from __future__ import annotations

from pathlib import Path

import cloud_llm_client
import local_llm_client
from model_router import ModelTier


def _required_config(config: dict, key: str) -> str:
    """Return a required model config value with a useful failure reason."""
    value = config.get(key)
    if value is None or str(value).strip() == "":
        raise local_llm_client.LocalLLMUnavailable(f"{key} is not set.")
    return str(value)


def _float_config(config: dict, key: str, default: float) -> float:
    """Return an optional float config value."""
    value = config.get(key)
    if value is None or str(value).strip() == "":
        return default
    return float(value)


def _int_config(config: dict, key: str, default: int) -> int:
    """Return an optional integer config value."""
    value = config.get(key)
    if value is None or str(value).strip() == "":
        return default
    return int(value)


def assemble_prompt(template_path: str, task_context: str) -> str:
    """Return a placeholder rendered prompt."""
    _ = (template_path, task_context)
    return ""


def run_model_prompt(template_path: str, context: str, model_tier: object, config: dict) -> str:
    """Render a prompt template and send it to the selected model tier."""
    template = Path(template_path).read_text(encoding="utf-8")
    rendered_prompt = template.replace("{task_context}", context)
    tier = model_tier if isinstance(model_tier, ModelTier) else ModelTier(str(model_tier))

    if tier == ModelTier.LOCAL_LOW:
        return local_llm_client.complete(
            rendered_prompt,
            _required_config(config, "LOCAL_LLM_LOW_MODEL"),
            _required_config(config, "LOCAL_LLM_BASE_URL"),
            max_tokens=_int_config(config, "LOCAL_LLM_LOW_MAX_TOKENS", 256),
            timeout=_float_config(config, "LOCAL_LLM_LOW_TIMEOUT_SECONDS", 30),
        )
    if tier == ModelTier.LOCAL_MEDIUM:
        return local_llm_client.complete(
            rendered_prompt,
            _required_config(config, "LOCAL_LLM_MEDIUM_MODEL"),
            _required_config(config, "LOCAL_LLM_BASE_URL"),
            max_tokens=_int_config(config, "LOCAL_LLM_MEDIUM_MAX_TOKENS", 600),
            timeout=_float_config(config, "LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS", 180),
        )
    if tier == ModelTier.CLOUD_HIGH:
        return cloud_llm_client.complete(
            rendered_prompt,
            config["CLOUD_HIGH_MODEL"],
            config.get("OPENAI_API_KEY"),
        )
    if tier == ModelTier.CLOUD_EXTRA_HIGH:
        return cloud_llm_client.complete(
            rendered_prompt,
            config["CLOUD_EXTRA_HIGH_MODEL"],
            config.get("OPENAI_API_KEY"),
        )

    raise ValueError(f"Unsupported model tier: {model_tier}")
