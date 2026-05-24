from __future__ import annotations

import sys
import os
import unittest
from pathlib import Path
import tempfile


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import orchestrator


class CodexPromptContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {
            "CODEX_MODEL": os.environ.get("CODEX_MODEL"),
            "CODEX_ENABLE_SEARCH": os.environ.get("CODEX_ENABLE_SEARCH"),
            "CODEX_CLI_PATH": os.environ.get("CODEX_CLI_PATH"),
        }

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_format_task_context_includes_required_contract_fields(self) -> None:
        prompt_context = orchestrator.format_task_context(
            {
                "id": 38,
                "title": "Implement AI router core",
                "goal": "Centralize model invocation.",
                "files": ["apps/ai_router/router.py"],
                "done_criteria": "router fails closed.",
            }
        )

        for field in orchestrator.REQUIRED_CODEX_PROMPT_FIELDS:
            self.assertIn(field, prompt_context)
        self.assertIn("- apps/ai_router/router.py", prompt_context)
        self.assertEqual(orchestrator.lint_codex_prompt_contract(prompt_context), [])

    def test_lint_codex_prompt_contract_blocks_missing_fields_and_vague_phrases(self) -> None:
        issues = orchestrator.lint_codex_prompt_contract(
            "TASK_ID: 38\nTASK_TITLE: Missing the rest\nFix the issue. Do the right thing."
        )

        self.assertIn("missing required field: OBJECTIVE:", issues)
        self.assertIn("blocked vague phrase: fix the issue", issues)
        self.assertIn("blocked vague phrase: do the right thing", issues)

    def test_build_codex_exec_command_includes_optional_model_and_search(self) -> None:
        os.environ["CODEX_MODEL"] = "gpt-5.5"
        os.environ["CODEX_ENABLE_SEARCH"] = "true"
        os.environ["CODEX_CLI_PATH"] = "codex"
        with tempfile.TemporaryDirectory() as temp_dir:
            project_root = Path(temp_dir)
            output_path = project_root / "agent-orchestrator" / "codex_last_message.md"

            command = orchestrator._build_codex_exec_command(project_root, output_path)

        self.assertTrue(Path(command[0]).name.lower().startswith("codex"))
        self.assertEqual(command[1:3], ["--search", "exec"])
        self.assertIn("-m", command)
        self.assertIn("gpt-5.5", command)
        self.assertEqual(command[-1], "-")


if __name__ == "__main__":
    unittest.main()
