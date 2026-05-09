from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import validator


class ValidatorMakeTargetTests(unittest.TestCase):
    def test_missing_make_target_messages_are_warnings(self) -> None:
        for output in (
            "make: *** No rule for target 'lint'.  Stop.",
            "make:  No rule to make target 'lint'.  Stop.",
        ):
            with self.subTest(output=output):
                errors: list[str] = []
                warnings: list[str] = []
                original_run = validator._run
                try:
                    validator._run = lambda command, cwd: subprocess.CompletedProcess(
                        command,
                        2,
                        stdout="",
                        stderr=output,
                    )
                    with tempfile.TemporaryDirectory() as temp_dir:
                        validator._make_check("lint", Path(temp_dir), errors, warnings)
                finally:
                    validator._run = original_run

                self.assertEqual(errors, [])
                self.assertEqual(warnings, ["Skipped make lint: target does not exist."])

    def test_non_missing_make_failure_is_error(self) -> None:
        errors: list[str] = []
        warnings: list[str] = []
        original_run = validator._run
        try:
            validator._run = lambda command, cwd: subprocess.CompletedProcess(
                command,
                2,
                stdout="",
                stderr="pytest failed",
            )
            with tempfile.TemporaryDirectory() as temp_dir:
                validator._make_check("test", Path(temp_dir), errors, warnings)
        finally:
            validator._run = original_run

        self.assertEqual(warnings, [])
        self.assertEqual(errors, ["make test failed:\npytest failed"])


class ValidatorSecretScanTests(unittest.TestCase):
    def test_secret_scan_ignores_bare_token_words(self) -> None:
        diff_patch = "\n".join(
            [
                "diff --git a/agent-orchestrator/last_prompt.md b/agent-orchestrator/last_prompt.md",
                "+++ b/agent-orchestrator/last_prompt.md",
                "+Done criteria: each call logs prompt version, token/cost estimate, and job context.",
                "+**Notes:** Potential secret pattern found in diff: token",
            ]
        )

        self.assertEqual(validator._secret_findings(diff_patch), [])

    def test_secret_scan_flags_secret_like_assignments_without_value(self) -> None:
        diff_patch = "\n".join(
            [
                "diff --git a/app.py b/app.py",
                "+++ b/app.py",
                "+DISCORD_BOT_TOKEN=abc123456789.supersecret",
                "+OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')",
                "+EXAMPLE_TOKEN=",
            ]
        )

        self.assertEqual(
            validator._secret_findings(diff_patch),
            ["app.py: secret-like assignment for `DISCORD_BOT_TOKEN`"],
        )

    def test_secret_scan_ignores_metrics_and_placeholders(self) -> None:
        diff_patch = "\n".join(
            [
                "diff --git a/config.example.yaml b/config.example.yaml",
                "+++ b/config.example.yaml",
                "+prompt_tokens: 123",
                "+DISCORD_BOT_TOKEN=your-token-here",
                "+api_key: <your api key>",
            ]
        )

        self.assertEqual(validator._secret_findings(diff_patch), [])

    def test_secret_scan_ignores_internal_diagnostic_variable_names(self) -> None:
        diff_patch = "\n".join(
            [
                "diff --git a/validator.py b/validator.py",
                "+++ b/validator.py",
                "+secret_findings = _secret_findings(diff_patch)",
                "+token_budget = estimate_tokens(prompt)",
            ]
        )

        self.assertEqual(validator._secret_findings(diff_patch), [])


if __name__ == "__main__":
    unittest.main()
