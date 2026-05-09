from __future__ import annotations

import os
import unittest

import discord_notifier


class DiscordNotifierTests(unittest.TestCase):
    def test_notify_uses_mock_mode_without_webhook(self) -> None:
        self.assertEqual(discord_notifier._deliver("test", webhook_url=""), "mock")

    def test_webhook_retries_transient_503(self) -> None:
        old_requests = discord_notifier.requests
        old_sleep = discord_notifier.time.sleep
        old_attempts = os.environ.get("DISCORD_WEBHOOK_RETRY_ATTEMPTS")
        os.environ["DISCORD_WEBHOOK_RETRY_ATTEMPTS"] = "3"

        class FakeResponse:
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code
                self.text = "temporary"
                self.headers = {}

        class FakeRequests:
            RequestException = RuntimeError

            def __init__(self) -> None:
                self.calls = 0

            def post(self, *args: object, **kwargs: object) -> FakeResponse:
                self.calls += 1
                if self.calls == 1:
                    return FakeResponse(503)
                return FakeResponse(204)

        fake_requests = FakeRequests()
        try:
            discord_notifier.requests = fake_requests
            discord_notifier.time.sleep = lambda _seconds: None
            self.assertEqual(discord_notifier._deliver("test", webhook_url="https://example.test"), "delivered")
            self.assertEqual(fake_requests.calls, 2)
        finally:
            discord_notifier.requests = old_requests
            discord_notifier.time.sleep = old_sleep
            if old_attempts is None:
                os.environ.pop("DISCORD_WEBHOOK_RETRY_ATTEMPTS", None)
            else:
                os.environ["DISCORD_WEBHOOK_RETRY_ATTEMPTS"] = old_attempts

    def test_webhook_does_not_retry_non_transient_404(self) -> None:
        old_requests = discord_notifier.requests
        old_attempts = os.environ.get("DISCORD_WEBHOOK_RETRY_ATTEMPTS")
        os.environ["DISCORD_WEBHOOK_RETRY_ATTEMPTS"] = "3"

        class FakeResponse:
            status_code = 404
            text = "unknown webhook"
            headers: dict[str, str] = {}

        class FakeRequests:
            RequestException = RuntimeError

            def __init__(self) -> None:
                self.calls = 0

            def post(self, *args: object, **kwargs: object) -> FakeResponse:
                self.calls += 1
                return FakeResponse()

        fake_requests = FakeRequests()
        try:
            discord_notifier.requests = fake_requests
            self.assertEqual(discord_notifier._deliver("test", webhook_url="https://example.test"), "error")
            self.assertEqual(fake_requests.calls, 1)
        finally:
            discord_notifier.requests = old_requests
            if old_attempts is None:
                os.environ.pop("DISCORD_WEBHOOK_RETRY_ATTEMPTS", None)
            else:
                os.environ["DISCORD_WEBHOOK_RETRY_ATTEMPTS"] = old_attempts

    @unittest.skipUnless(
        os.getenv("RUN_DISCORD_WEBHOOK_TEST") == "1",
        "Set RUN_DISCORD_WEBHOOK_TEST=1 to send a real Discord webhook test.",
    )
    def test_real_webhook_delivery_when_explicitly_enabled(self) -> None:
        webhook_url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
        self.assertTrue(webhook_url, "DISCORD_WEBHOOK_URL must be set for the real webhook test.")
        result = discord_notifier._deliver(
            "[ORCHESTRATOR TEST] Discord webhook is working.",
            webhook_url=webhook_url,
        )
        self.assertEqual(result, "delivered")


if __name__ == "__main__":
    unittest.main()
