from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import prompt_runner
from model_router import ModelTier


class PromptRunnerLocalTierConfigTests(unittest.TestCase):
    def test_local_low_uses_low_timeout_and_token_budget(self) -> None:
        old_complete = prompt_runner.local_llm_client.complete
        calls: list[dict[str, object]] = []
        try:
            prompt_runner.local_llm_client.complete = (
                lambda prompt, model, base_url, **kwargs: calls.append(
                    {"prompt": prompt, "model": model, "base_url": base_url, **kwargs}
                )
                or "ok"
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                template_path = Path(temp_dir) / "prompt.md"
                template_path.write_text("Explain:\n{task_context}", encoding="utf-8")
                result = prompt_runner.run_model_prompt(
                    str(template_path),
                    "status context",
                    ModelTier.LOCAL_LOW,
                    {
                        "LOCAL_LLM_BASE_URL": "http://localhost:11434/v1",
                        "LOCAL_LLM_LOW_MODEL": "small:latest",
                        "LOCAL_LLM_LOW_TIMEOUT_SECONDS": "30",
                        "LOCAL_LLM_LOW_MAX_TOKENS": "256",
                        "LOCAL_LLM_LOW_KEEP_ALIVE": "30m",
                    },
                )
        finally:
            prompt_runner.local_llm_client.complete = old_complete

        self.assertEqual(result, "ok")
        self.assertEqual(calls[0]["model"], "small:latest")
        self.assertEqual(calls[0]["timeout"], 30.0)
        self.assertEqual(calls[0]["max_tokens"], 256)
        self.assertEqual(calls[0]["keep_alive"], "30m")


if __name__ == "__main__":
    unittest.main()
