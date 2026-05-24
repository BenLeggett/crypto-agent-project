from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import orchestrator


class RunLoopManualModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._old_env = {
            "CODEX_MODE": os.environ.get("CODEX_MODE"),
            "PROJECT_ROOT": os.environ.get("PROJECT_ROOT"),
            "LOOP_INTERVAL_SECONDS": os.environ.get("LOOP_INTERVAL_SECONDS"),
            "LOCAL_VALIDATION_SUMMARY": os.environ.get("LOCAL_VALIDATION_SUMMARY"),
            "CODEX_TIMEOUT_SECONDS": os.environ.get("CODEX_TIMEOUT_SECONDS"),
            "MAX_AUTO_TASKS_PER_SESSION": os.environ.get("MAX_AUTO_TASKS_PER_SESSION"),
            "CODEX_LAST_MESSAGE_PATH": os.environ.get("CODEX_LAST_MESSAGE_PATH"),
            "CODEX_MODEL": os.environ.get("CODEX_MODEL"),
            "CODEX_ENABLE_SEARCH": os.environ.get("CODEX_ENABLE_SEARCH"),
            "CODEX_CLI_PATH": os.environ.get("CODEX_CLI_PATH"),
        }
        os.environ["CODEX_MODE"] = "manual"
        os.environ["PROJECT_ROOT"] = ".."
        os.environ["LOOP_INTERVAL_SECONDS"] = "1"
        os.environ["LOCAL_VALIDATION_SUMMARY"] = "failures_only"
        os.environ["CODEX_TIMEOUT_SECONDS"] = "30"
        os.environ["MAX_AUTO_TASKS_PER_SESSION"] = "5"
        os.environ["CODEX_LAST_MESSAGE_PATH"] = "agent-orchestrator/codex_last_message.md"
        os.environ["CODEX_MODEL"] = ""
        os.environ["CODEX_ENABLE_SEARCH"] = "false"
        os.environ["CODEX_CLI_PATH"] = "codex"

        self._old_notify = orchestrator.discord_notifier.notify
        self._old_validate = orchestrator.validator.validate
        self._old_assemble_prompt = orchestrator.prompt_runner.assemble_prompt
        self._old_run_model_prompt = orchestrator.prompt_runner.run_model_prompt
        self._old_subprocess_run = orchestrator.subprocess.run
        self._old_sleep = orchestrator.time.sleep
        self.notifications: list[str] = []
        self.validation_calls: list[str] = []
        self.assemble_calls: list[tuple[str, str, str]] = []
        self.medium_review_calls: list[tuple[str, dict]] = []

        orchestrator.discord_notifier.notify = self.notifications.append
        orchestrator.time.sleep = lambda _seconds: None

    def tearDown(self) -> None:
        for key, value in self._old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        orchestrator.discord_notifier.notify = self._old_notify
        orchestrator.validator.validate = self._old_validate
        orchestrator.prompt_runner.assemble_prompt = self._old_assemble_prompt
        orchestrator.prompt_runner.run_model_prompt = self._old_run_model_prompt
        orchestrator.subprocess.run = self._old_subprocess_run
        orchestrator.time.sleep = self._old_sleep

    def _write_project(self, root: Path) -> Path:
        orchestrator_root = root / "agent-orchestrator"
        docs_root = root / "docs"
        prompts_root = orchestrator_root / "prompts"
        docs_root.mkdir()
        prompts_root.mkdir(parents=True)
        (docs_root / "PHASE_TASK_MAP.md").write_text(
            "\n".join(
                [
                    "## Phase 10 - AI router and cost controls",
                    "",
                    "### Primary tasks",
                    "- 38. Implement AI router core",
                    "",
                    "## Phase 11 - Model-informed paper decisioning",
                    "",
                    "### Primary tasks",
                    "- 39. Implement model-informed paper proposal job",
                ]
            ),
            encoding="utf-8",
        )
        (docs_root / "TASK_QUEUE.md").write_text(
            "\n".join(
                [
                    "# Task Queue",
                    "",
                    "## 38. Implement AI router core",
                    "- Goal: Build the AI router.",
                    "- Files likely affected: `apps/ai_router/router.py`",
                    "- Dependencies: none",
                    "- Done criteria: router supports approved providers.",
                    "",
                    "## 39. Implement model-informed paper proposal job",
                    "- Goal: Build the proposal job.",
                    "- Files likely affected: `apps/report_jobs/model_paper.py`",
                    "- Dependencies: 38",
                    "- Done criteria: paper proposals are generated.",
                ]
            ),
            encoding="utf-8",
        )
        (prompts_root / "run_next_task.md").write_text(
            "Prompt:\n{task_context}\n",
            encoding="utf-8",
        )
        (prompts_root / "failed_task_diagnosis.md").write_text(
            "Diagnose:\n{task_context}\n",
            encoding="utf-8",
        )
        (root / "ACTIVITY.MD").write_text(
            "## 2026-05-09\n- Previous orchestrator action.\n",
            encoding="utf-8",
        )
        orchestrator.init_state_db(orchestrator_root / "state.sqlite")
        return orchestrator_root

    def _seed_task(self, db_path: Path, status: str) -> None:
        connection = sqlite3.connect(db_path)
        try:
            connection.execute(
                """
                INSERT INTO tasks (task_id, phase, title, status, notes)
                VALUES (38, 'Phase 10 - AI router and cost controls', 'Implement AI router core', ?, 'test seed')
                """,
                (status,),
            )
            connection.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('paused', '0')"
            )
            connection.commit()
        finally:
            connection.close()

    def _status_and_paused(self, db_path: Path) -> tuple[str, str]:
        connection = sqlite3.connect(db_path)
        try:
            status = connection.execute(
                "SELECT status FROM tasks WHERE task_id = 38"
            ).fetchone()[0]
            paused = connection.execute(
                "SELECT value FROM settings WHERE key = 'paused'"
            ).fetchone()[0]
        finally:
            connection.close()
        return str(status), str(paused)

    def _operator_events(self, db_path: Path) -> list[tuple[str, str, str]]:
        connection = sqlite3.connect(db_path)
        try:
            rows = connection.execute(
                """
                SELECT event_type, status, summary
                FROM operator_events
                ORDER BY event_id
                """
            ).fetchall()
        finally:
            connection.close()
        return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]

    def test_manual_pending_task_writes_prompt_and_pauses_without_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "pending")

            def assemble(template_path: str, task_context: str, output_path: str) -> str:
                self.assemble_calls.append((template_path, task_context, output_path))
                rendered = Path(template_path).read_text(encoding="utf-8").replace(
                    "{task_context}",
                    task_context,
                )
                Path(output_path).write_text(rendered, encoding="utf-8")
                return rendered

            orchestrator.prompt_runner.assemble_prompt = assemble
            orchestrator.validator.validate = lambda project_root: self.validation_calls.append(project_root)

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "in_progress")
            self.assertEqual(paused, "1")
            self.assertEqual(len(self.assemble_calls), 1)
            self.assertEqual(self.validation_calls, [])
            self.assertTrue((orchestrator_root / "last_prompt.md").exists())
            events = self._operator_events(db_path)
            event_types = [row[0] for row in events]
            self.assertIn("prompt_ready", event_types)
            self.assertIn("paused", event_types)
            self.assertEqual(self.notifications, [])

            connection = sqlite3.connect(db_path)
            try:
                current_phase = connection.execute(
                    "SELECT value FROM settings WHERE key = 'current_phase'"
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(current_phase, ("Phase 10 - AI router and cost controls",))

    def test_manual_in_progress_task_resumes_with_validation_without_reprompting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "in_progress")

            orchestrator.prompt_runner.assemble_prompt = lambda *args: self.assemble_calls.append(args)

            def validate(project_root: str) -> dict[str, object]:
                self.validation_calls.append(project_root)
                return {
                    "passed": True,
                    "errors": [],
                    "warnings": [],
                    "diff_summary": "",
                }

            orchestrator.validator.validate = validate

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "done")
            self.assertEqual(paused, "0")
            self.assertEqual(self.assemble_calls, [])
            self.assertEqual(len(self.validation_calls), 1)
            event_types = [row[0] for row in self._operator_events(db_path)]
            self.assertIn("resume_received", event_types)
            self.assertIn("validating", event_types)
            self.assertIn("task_done", event_types)
            self.assertEqual(self.notifications, [])

    def test_manual_validation_failure_pauses_without_medium_review(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "in_progress")
            (orchestrator_root / "last_prompt.md").write_text(
                "Repair task 38 using deterministic validation.",
                encoding="utf-8",
            )

            orchestrator.prompt_runner.assemble_prompt = lambda *args: self.assemble_calls.append(args)
            orchestrator.validator.validate = lambda project_root: {
                "passed": False,
                "errors": ["make test failed"],
                "warnings": [],
                "diff_summary": "agent-orchestrator/orchestrator.py | 12 ++++++",
            }
            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "failed")
            self.assertEqual(paused, "1")
            self.assertEqual(self.assemble_calls, [])
            self.assertEqual(self.medium_review_calls, [])
            event_types = [row[0] for row in self._operator_events(db_path)]
            failure_index = event_types.index("validation_failed")
            paused_index = event_types.index("paused")
            self.assertLess(failure_index, paused_index)
            self.assertNotIn("medium_review_running", event_types)
            self.assertNotIn("medium_review_done", event_types)
            self.assertEqual(self.notifications, [])

    def test_manual_validation_failure_records_failure_details_for_listener_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "in_progress")

            orchestrator.prompt_runner.assemble_prompt = lambda *args: self.assemble_calls.append(args)
            orchestrator.validator.validate = lambda project_root: {
                "passed": False,
                "errors": ["make lint failed"],
                "warnings": [],
                "diff_summary": "agent-orchestrator/discord_listener.py | 4 ++",
            }

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "failed")
            self.assertEqual(paused, "1")
            self.assertEqual(self.assemble_calls, [])
            events = self._operator_events(db_path)
            event_types = [row[0] for row in events]
            self.assertIn("validation_failed", event_types)
            self.assertIn("paused", event_types)
            self.assertNotIn("medium_review_running", event_types)
            self.assertTrue(any("make lint failed" in row[2] for row in events))
            self.assertEqual(self.notifications, [])

    def test_manual_failed_task_resume_revalidates_without_reprompting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "failed")

            orchestrator.prompt_runner.assemble_prompt = lambda *args: self.assemble_calls.append(args)

            def validate(project_root: str) -> dict[str, object]:
                self.validation_calls.append(project_root)
                return {
                    "passed": True,
                    "errors": [],
                    "warnings": [],
                    "diff_summary": "",
                }

            orchestrator.validator.validate = validate

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "done")
            self.assertEqual(paused, "0")
            self.assertEqual(self.assemble_calls, [])
            self.assertEqual(len(self.validation_calls), 1)

    def test_phase_gate_blocks_next_phase_after_current_phase_done(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    INSERT INTO tasks (task_id, phase, title, status, notes)
                    VALUES (38, 'Phase 10 - AI router and cost controls', 'Implement AI router core', 'done', 'done')
                    """
                )
                connection.execute(
                    """
                    INSERT INTO tasks (task_id, phase, title, status, notes)
                    VALUES (39, 'Phase 11 - Model-informed paper decisioning', 'Implement model-informed paper proposal job', 'pending', 'pending')
                    """
                )
                connection.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('current_phase', 'Phase 10 - AI router and cost controls')"
                )
                connection.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('paused', '0')"
                )
                connection.commit()
            finally:
                connection.close()

            self._old_phase_review_result = orchestrator._phase_review_result
            self._old_wait_for_approval = orchestrator.decision_gate.wait_for_approval
            self._old_record_decision = orchestrator.decision_gate.record_decision
            try:
                orchestrator._phase_review_result = lambda *args: "Phase 10 complete."
                orchestrator.decision_gate.wait_for_approval = lambda *args: True
                decisions: list[tuple] = []
                orchestrator.decision_gate.record_decision = lambda *args: decisions.append(args)
                orchestrator.prompt_runner.assemble_prompt = lambda *args: self.assemble_calls.append(args)

                self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)
            finally:
                orchestrator._phase_review_result = self._old_phase_review_result
                orchestrator.decision_gate.wait_for_approval = self._old_wait_for_approval
                orchestrator.decision_gate.record_decision = self._old_record_decision

            self.assertEqual(self.assemble_calls, [])
            events = self._operator_events(db_path)
            self.assertTrue(any(row[0] == "approval_required" and "phase-10-exit" in row[2] for row in events))

            connection = sqlite3.connect(db_path)
            try:
                current_phase = connection.execute(
                    "SELECT value FROM settings WHERE key = 'current_phase'"
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(current_phase, ("Phase 11 - Model-informed paper decisioning",))

    def test_auto_mode_invokes_codex_exec_stdin_then_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CODEX_MODE"] = "auto"
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "pending")
            calls: list[dict[str, object]] = []

            def fake_run(command: list[str], **kwargs: object) -> object:
                calls.append({"command": command, **kwargs})
                output_path = Path(command[command.index("-o") + 1])
                output_path.write_text("Codex finished.", encoding="utf-8")
                return orchestrator.subprocess.CompletedProcess(command, 0, "stdout ok", "")

            orchestrator.subprocess.run = fake_run
            orchestrator.validator.validate = lambda project_root: {
                "passed": True,
                "errors": [],
                "warnings": [],
                "diff_summary": "",
            }

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            self.assertEqual(len(calls), 1)
            command = calls[0]["command"]
            self.assertIsInstance(command, list)
            self.assertTrue(Path(command[0]).name.lower().startswith("codex"))
            self.assertIn("exec", command)
            self.assertIn("-C", command)
            self.assertIn("workspace-write", command)
            self.assertIn('approval_policy="never"', command)
            self.assertEqual(command[-1], "-")
            self.assertIn("TASK_ID: 38", str(calls[0]["input"]))
            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "done")
            self.assertEqual(paused, "0")
            self.assertTrue(any("Running Codex" in item for item in self.notifications))
            self.assertTrue(any("complete" in item for item in self.notifications))

    def test_auto_mode_blocks_underspecified_prompt_before_codex(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CODEX_MODE"] = "auto"
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "pending")

            def assemble(template_path: str, task_context: str, output_path: str) -> str:
                _ = (template_path, task_context)
                rendered = "Fix the issue in the project. Do the right thing."
                Path(output_path).write_text(rendered, encoding="utf-8")
                return rendered

            orchestrator.prompt_runner.assemble_prompt = assemble
            orchestrator.subprocess.run = lambda *args, **kwargs: self.fail("Codex must not be invoked")

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "in_progress")
            self.assertEqual(paused, "1")
            self.assertTrue(any("PROMPT BLOCKED" in item for item in self.notifications))
            connection = sqlite3.connect(db_path)
            try:
                awaiting = connection.execute(
                    "SELECT value FROM settings WHERE key = 'awaiting_clarification_task_id'"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual(awaiting, ("38",))

    def test_auto_mode_timeout_pauses_without_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CODEX_MODE"] = "auto"
            os.environ["CODEX_TIMEOUT_SECONDS"] = "5"
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "pending")
            orchestrator.subprocess.run = lambda *args, **kwargs: (_ for _ in ()).throw(
                orchestrator.subprocess.TimeoutExpired(args[0], 5, output="partial")
            )
            orchestrator.validator.validate = lambda project_root: self.validation_calls.append(project_root)

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "in_progress")
            self.assertEqual(paused, "1")
            self.assertEqual(self.validation_calls, [])
            self.assertTrue(any("CODEX TIMEOUT" in item for item in self.notifications))

    def test_auto_mode_missing_codex_cli_pauses_without_unhandled_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CODEX_MODE"] = "auto"
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "pending")
            orchestrator.subprocess.run = lambda *args, **kwargs: (_ for _ in ()).throw(
                FileNotFoundError("codex")
            )
            orchestrator.validator.validate = lambda project_root: self.validation_calls.append(project_root)

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "in_progress")
            self.assertEqual(paused, "1")
            self.assertEqual(self.validation_calls, [])
            self.assertTrue(any("CODEX FAILURE" in item for item in self.notifications))
            events = self._operator_events(db_path)
            self.assertTrue(any(row[0] == "codex_failure" for row in events))

    def test_auto_mode_clarification_marker_pauses_without_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CODEX_MODE"] = "auto"
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "pending")

            def fake_run(command: list[str], **kwargs: object) -> object:
                output_path = Path(command[command.index("-o") + 1])
                output_path.write_text(
                    "CODEX_NEEDS_CLARIFICATION:\nWhich file should be changed?",
                    encoding="utf-8",
                )
                return orchestrator.subprocess.CompletedProcess(command, 0, "", "")

            orchestrator.subprocess.run = fake_run
            orchestrator.validator.validate = lambda project_root: self.validation_calls.append(project_root)

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "in_progress")
            self.assertEqual(paused, "1")
            self.assertEqual(self.validation_calls, [])
            self.assertTrue(any("CODEX QUESTION" in item for item in self.notifications))

    def test_auto_mode_nonzero_exit_pauses_without_validation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CODEX_MODE"] = "auto"
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "pending")
            orchestrator.subprocess.run = lambda command, **kwargs: orchestrator.subprocess.CompletedProcess(
                command,
                2,
                "stdout",
                "stderr",
            )
            orchestrator.validator.validate = lambda project_root: self.validation_calls.append(project_root)

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=1), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "in_progress")
            self.assertEqual(paused, "1")
            self.assertEqual(self.validation_calls, [])
            self.assertTrue(any("CODEX FAILURE" in item for item in self.notifications))

    def test_auto_mode_session_limit_pauses_after_successful_cycle(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            os.environ["CODEX_MODE"] = "auto"
            os.environ["MAX_AUTO_TASKS_PER_SESSION"] = "1"
            orchestrator_root = self._write_project(Path(temp_dir))
            db_path = orchestrator_root / "state.sqlite"
            self._seed_task(db_path, "pending")

            def fake_run(command: list[str], **kwargs: object) -> object:
                output_path = Path(command[command.index("-o") + 1])
                output_path.write_text("done", encoding="utf-8")
                return orchestrator.subprocess.CompletedProcess(command, 0, "", "")

            orchestrator.subprocess.run = fake_run
            orchestrator.validator.validate = lambda project_root: {
                "passed": True,
                "errors": [],
                "warnings": [],
                "diff_summary": "",
            }

            self.assertEqual(orchestrator.run_loop(orchestrator_root, max_iterations=3), 0)

            status, paused = self._status_and_paused(db_path)
            self.assertEqual(status, "done")
            self.assertEqual(paused, "1")
            self.assertTrue(any("Session limit reached" in item for item in self.notifications))


if __name__ == "__main__":
    unittest.main()
