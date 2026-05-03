from __future__ import annotations

from pathlib import Path

import cloud_llm_client
import local_llm_client
from model_router import ModelTier


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
            config["LOCAL_LLM_LOW_MODEL"],
            config["LOCAL_LLM_BASE_URL"],
        )
    if tier == ModelTier.LOCAL_MEDIUM:
        return local_llm_client.complete(
            rendered_prompt,
            config["LOCAL_LLM_MEDIUM_MODEL"],
            config["LOCAL_LLM_BASE_URL"],
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
