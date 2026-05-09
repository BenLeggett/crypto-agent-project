from __future__ import annotations

import sys
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import validation_failure_review


class ValidationFailureReviewTests(unittest.TestCase):
    def test_review_warms_medium_model_before_review_call(self) -> None:
        old_warmup = validation_failure_review.local_llm_client.warmup_model
        old_complete = validation_failure_review.local_llm_client.complete
        calls: list[tuple[str, dict[str, object]]] = []
        try:
            validation_failure_review.local_llm_client.warmup_model = (
                lambda model, base_url, timeout: calls.append(
                    ("warmup", {"model": model, "base_url": base_url, "timeout": timeout})
                )
                or True
            )
            validation_failure_review.local_llm_client.complete = (
                lambda prompt, model, base_url, **kwargs: calls.append(
                    (
                        "complete",
                        {
                            "prompt": prompt,
                            "model": model,
                            "base_url": base_url,
                            **kwargs,
                        },
                    )
                )
                or "Probable cause: test failure."
            )

            result = validation_failure_review.review_validation_failure_with_medium_model(
                "Task 38 failed make test.",
                {
                    "LOCAL_LLM_BASE_URL": "http://localhost:11434/v1",
                    "LOCAL_LLM_MEDIUM_MODEL": "gemma4:latest",
                    "LOCAL_LLM_MEDIUM_WARMUP_TIMEOUT_SECONDS": "120",
                    "LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS": "180",
                    "LOCAL_LLM_MEDIUM_MAX_TOKENS": "600",
                },
            )
        finally:
            validation_failure_review.local_llm_client.warmup_model = old_warmup
            validation_failure_review.local_llm_client.complete = old_complete

        self.assertTrue(result["review_available"])
        self.assertEqual(result["model_used"], "gemma4:latest")
        self.assertEqual(calls[0][0], "warmup")
        self.assertEqual(calls[0][1]["timeout"], 120.0)
        self.assertEqual(calls[1][0], "complete")
        self.assertIn("Probable cause", str(calls[1][1]["prompt"]))
        self.assertEqual(calls[1][1]["timeout"], 180.0)
        self.assertEqual(calls[1][1]["max_tokens"], 600)

    def test_review_returns_unavailable_when_warmup_fails(self) -> None:
        old_warmup = validation_failure_review.local_llm_client.warmup_model
        old_complete = validation_failure_review.local_llm_client.complete
        try:
            validation_failure_review.local_llm_client.warmup_model = lambda *args, **kwargs: False
            validation_failure_review.local_llm_client.complete = lambda *args, **kwargs: self.fail(
                "review call should not run after failed warmup"
            )

            result = validation_failure_review.review_validation_failure_with_medium_model(
                "Task failed.",
                {
                    "LOCAL_LLM_BASE_URL": "http://localhost:11434/v1",
                    "LOCAL_LLM_MEDIUM_MODEL": "gemma4:latest",
                },
            )
        finally:
            validation_failure_review.local_llm_client.warmup_model = old_warmup
            validation_failure_review.local_llm_client.complete = old_complete

        self.assertFalse(result["review_available"])
        self.assertEqual(result["model_used"], "none")
        self.assertTrue(result["fallback_recommended"])
        self.assertIn("warmup", str(result["summary"]))

    def test_review_returns_unavailable_when_model_response_is_empty(self) -> None:
        old_warmup = validation_failure_review.local_llm_client.warmup_model
        old_complete = validation_failure_review.local_llm_client.complete
        try:
            validation_failure_review.local_llm_client.warmup_model = lambda *args, **kwargs: True
            validation_failure_review.local_llm_client.complete = lambda *args, **kwargs: "   "

            result = validation_failure_review.review_validation_failure_with_medium_model(
                "Task failed.",
                {
                    "LOCAL_LLM_BASE_URL": "http://localhost:11434/v1",
                    "LOCAL_LLM_MEDIUM_MODEL": "gemma4:latest",
                },
            )
        finally:
            validation_failure_review.local_llm_client.warmup_model = old_warmup
            validation_failure_review.local_llm_client.complete = old_complete

        self.assertFalse(result["review_available"])
        self.assertEqual(result["model_used"], "none")
        self.assertTrue(result["fallback_recommended"])
        self.assertIn("empty response", str(result["summary"]))


if __name__ == "__main__":
    unittest.main()
