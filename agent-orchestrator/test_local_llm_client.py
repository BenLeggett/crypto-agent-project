from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import local_llm_client


class LocalLLMClientTests(unittest.TestCase):
    def test_complete_retries_connection_failure_and_returns_content(self) -> None:
        old_requests = local_llm_client.requests
        old_sleep = local_llm_client.time.sleep
        old_attempts = os.environ.get("LOCAL_LLM_RETRY_ATTEMPTS")
        os.environ["LOCAL_LLM_RETRY_ATTEMPTS"] = "2"

        class FakeRequests:
            RequestException = RuntimeError

            def __init__(self) -> None:
                self.calls = 0

            def post(self, *args: object, **kwargs: object) -> object:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("model still loading")
                return FakeResponse()

        class FakeResponse:
            status_code = 200

            def json(self) -> dict[str, object]:
                return {"choices": [{"message": {"content": "OK"}}]}

        fake_requests = FakeRequests()
        try:
            local_llm_client.requests = fake_requests
            local_llm_client.time.sleep = lambda _seconds: None
            self.assertEqual(
                local_llm_client.complete(
                    "Reply with OK only.",
                    "gemma4:latest",
                    "http://localhost:11434/v1",
                ),
                "OK",
            )
            self.assertEqual(fake_requests.calls, 2)
        finally:
            local_llm_client.requests = old_requests
            local_llm_client.time.sleep = old_sleep
            if old_attempts is None:
                os.environ.pop("LOCAL_LLM_RETRY_ATTEMPTS", None)
            else:
                os.environ["LOCAL_LLM_RETRY_ATTEMPTS"] = old_attempts

    def test_complete_error_includes_underlying_exception(self) -> None:
        old_requests = local_llm_client.requests
        old_attempts = os.environ.get("LOCAL_LLM_RETRY_ATTEMPTS")
        os.environ["LOCAL_LLM_RETRY_ATTEMPTS"] = "1"

        class FakeTimeout(RuntimeError):
            pass

        class FakeRequests:
            RequestException = RuntimeError

            def post(self, *args: object, **kwargs: object) -> object:
                raise FakeTimeout("read timed out")

        try:
            local_llm_client.requests = FakeRequests()
            with self.assertRaises(local_llm_client.LocalLLMUnavailable) as error:
                local_llm_client.complete(
                    "Diagnose failure.",
                    "gemma4:latest",
                    "http://localhost:11434/v1",
                )
        finally:
            local_llm_client.requests = old_requests
            if old_attempts is None:
                os.environ.pop("LOCAL_LLM_RETRY_ATTEMPTS", None)
            else:
                os.environ["LOCAL_LLM_RETRY_ATTEMPTS"] = old_attempts

        self.assertIn("gemma4:latest", str(error.exception))
        self.assertIn("FakeTimeout: read timed out", str(error.exception))

    def test_warmup_model_uses_tiny_completion(self) -> None:
        old_complete = local_llm_client.complete
        calls: list[dict[str, object]] = []
        try:
            local_llm_client.complete = lambda prompt, model, base_url, **kwargs: calls.append(
                {
                    "prompt": prompt,
                    "model": model,
                    "base_url": base_url,
                    **kwargs,
                }
            ) or "ready"

            self.assertTrue(
                local_llm_client.warmup_model(
                    "gemma4:latest",
                    "http://localhost:11434/v1",
                    timeout=120,
                )
            )
        finally:
            local_llm_client.complete = old_complete

        self.assertEqual(calls[0]["prompt"], "Reply with exactly: ready")
        self.assertEqual(calls[0]["max_tokens"], 8)
        self.assertEqual(calls[0]["temperature"], 0.0)
        self.assertEqual(calls[0]["timeout"], 120)

    def test_warmup_model_returns_false_on_failure(self) -> None:
        old_complete = local_llm_client.complete
        try:
            def fail_complete(*args: object, **kwargs: object) -> str:
                raise local_llm_client.LocalLLMUnavailable("offline")

            local_llm_client.complete = fail_complete

            self.assertFalse(
                local_llm_client.warmup_model(
                    "gemma4:latest",
                    "http://localhost:11434/v1",
                    timeout=120,
                )
            )
        finally:
            local_llm_client.complete = old_complete


if __name__ == "__main__":
    unittest.main()
