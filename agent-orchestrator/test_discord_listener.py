from __future__ import annotations

import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent


def load_listener_module():
    dotenv_stub = types.ModuleType("dotenv")
    dotenv_stub.load_dotenv = lambda *args, **kwargs: None
    sys.modules["dotenv"] = dotenv_stub

    module_path = TEST_ROOT / "discord_listener.py"
    spec = importlib.util.spec_from_file_location("discord_listener", module_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load discord_listener.py for testing.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DiscordListenerTests(unittest.TestCase):
    def _create_project_db(self, root: Path) -> Path:
        orchestrator_root = root / "agent-orchestrator"
        orchestrator_root.mkdir()
        (root / "ACTIVITY.MD").write_text(
            "## 2026-05-09\n- Task 38 validation failed.\n",
            encoding="utf-8",
        )
        (orchestrator_root / "last_prompt.md").write_text(
            "Prompt for task 38.",
            encoding="utf-8",
        )
        db_path = orchestrator_root / "state.sqlite"
        connection = sqlite3.connect(db_path)
        try:
            connection.execute(
                """
                CREATE TABLE approvals (
                    approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER,
                    gate_type TEXT,
                    ref TEXT,
                    requested_at TEXT,
                    decided_at TEXT,
                    decision TEXT,
                    notes TEXT
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE tasks (
                    task_id INTEGER PRIMARY KEY,
                    phase TEXT,
                    title TEXT,
                    status TEXT,
                    attempts INTEGER DEFAULT 0,
                    last_run_id INTEGER,
                    notes TEXT
                )
                """
            )
            connection.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
            connection.execute(
                """
                INSERT INTO tasks (task_id, phase, title, status, notes)
                VALUES (38, 'Phase 10 - AI router and cost controls', 'Implement AI router core', 'failed', 'make test failed')
                """
            )
            connection.execute(
                "INSERT INTO settings (key, value) VALUES ('paused', '1')"
            )
            connection.commit()
        finally:
            connection.close()
        return db_path

    def _snapshot_rows(self, db_path: Path) -> dict[str, list[tuple]]:
        connection = sqlite3.connect(db_path)
        try:
            return {
                "tasks": connection.execute("SELECT * FROM tasks ORDER BY task_id").fetchall(),
                "settings": connection.execute("SELECT * FROM settings ORDER BY key").fetchall(),
                "approvals": connection.execute("SELECT * FROM approvals ORDER BY approval_id").fetchall(),
            }
        finally:
            connection.close()

    def test_resume_alias_and_pause_resume_round_trip(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "state.sqlite"
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    CREATE TABLE approvals (
                        approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
                        run_id INTEGER,
                        gate_type TEXT,
                        ref TEXT,
                        requested_at TEXT,
                        decided_at TEXT,
                        decision TEXT,
                        notes TEXT
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE tasks (
                        task_id INTEGER PRIMARY KEY,
                        phase TEXT,
                        title TEXT,
                        status TEXT,
                        attempts INTEGER DEFAULT 0,
                        last_run_id INTEGER,
                        notes TEXT
                    )
                    """
                )
                connection.commit()
            finally:
                connection.close()

            self.assertEqual(
                listener._parse_command_line("!reusme"),
                ("!resume", []),
            )
            self.assertEqual(
                listener._parse_command_line("!Resume"),
                ("!resume", []),
            )

            self.assertEqual(
                listener.handle_command("!pause", [], str(db_path)),
                "Orchestrator paused. Send !resume to continue.",
            )
            self.assertEqual(
                listener.handle_command("!resume", [], str(db_path)),
                "Orchestrator resumed.",
            )
            self.assertEqual(
                listener.handle_command("!resume", [], str(db_path)),
                "Orchestrator resumed.",
            )

            connection = sqlite3.connect(db_path)
            try:
                paused_value = connection.execute(
                    "SELECT value FROM settings WHERE key = 'paused'"
                ).fetchone()
            finally:
                connection.close()

            self.assertEqual(paused_value, ("0",))

    def test_explain_returns_local_model_summary_without_mutating_state(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._create_project_db(Path(temp_dir))
            before_rows = self._snapshot_rows(db_path)
            prompt_path = db_path.parent / "last_prompt.md"
            before_prompt = prompt_path.read_text(encoding="utf-8")

            old_run_model_prompt = listener.prompt_runner.run_model_prompt
            calls: list[tuple[str, str, object, dict]] = []
            try:
                listener.prompt_runner.run_model_prompt = (
                    lambda template_path, context, model_tier, config: calls.append(
                        (template_path, context, model_tier, config)
                    )
                    or "What happened:\nValidation failed after the manual prompt junction.\n\nNext:\nRepair and resume."
                )

                response = listener.handle_command("!explain", [], str(db_path))
            finally:
                listener.prompt_runner.run_model_prompt = old_run_model_prompt

            self.assertIn("What happened:", response)
            self.assertIn("manual prompt junction", response)
            self.assertEqual(len(calls), 1)
            self.assertIn("Current SQLite Status", calls[0][1])
            self.assertNotIn("Git Diff Summary", calls[0][1])
            self.assertEqual(self._snapshot_rows(db_path), before_rows)
            self.assertEqual(prompt_path.read_text(encoding="utf-8"), before_prompt)

    def test_explain_falls_back_when_local_model_fails(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._create_project_db(Path(temp_dir))
            old_run_model_prompt = listener.prompt_runner.run_model_prompt
            try:
                def fail_model(*args: object) -> str:
                    raise RuntimeError("local LLM down")

                listener.prompt_runner.run_model_prompt = fail_model
                response = listener.handle_command("!explain", [], str(db_path))
            finally:
                listener.prompt_runner.run_model_prompt = old_run_model_prompt

            self.assertIn("Deterministic explanation", response)
            self.assertIn("Local model note: RuntimeError: local LLM down", response)
            self.assertIn("Status: failed", response)

    def test_long_discord_responses_are_split_without_truncation(self) -> None:
        listener = load_listener_module()

        response = "x" * 5000
        chunks = listener._split_discord_messages(response)

        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= listener.DISCORD_RESPONSE_LIMIT for chunk in chunks))
        self.assertEqual("".join(chunks), response)

    def test_loading_messages_reflect_actions(self) -> None:
        listener = load_listener_module()

        self.assertIn("Explaining", listener._loading_message_for_command("!explain", []))
        self.assertIn("Resuming", listener._loading_message_for_command("!resume", []))
        self.assertIn("approval", listener._loading_message_for_command("!approve", ["phase-10-exit"]))

    def test_action_and_waiting_labels_describe_in_flight_state(self) -> None:
        listener = load_listener_module()

        self.assertEqual(listener._action_taken_for_command("!resume", []), "Resume")
        self.assertEqual(
            listener._action_taken_for_command("!approve", ["phase-10-exit"]),
            "Approve phase-10-exit",
        )
        self.assertEqual(
            listener._waiting_on_for_command("!explain"),
            "local explanation or deterministic fallback",
        )

    def test_webhook_update_kind_holds_controls_during_medium_review(self) -> None:
        listener = load_listener_module()

        failure_message = (
            "[ORCHESTRATOR · FAILURE] Task 38: Implement AI router core\n"
            "Validation failed:\n- make test failed"
        )

        self.assertEqual(
            listener._webhook_update_kind(failure_message),
            "validation_failure_review_expected",
        )
        self.assertEqual(
            listener._webhook_update_kind("[ORCHESTRATOR - MEDIUM REVIEW START]\nReviewing."),
            "medium_review_start",
        )
        self.assertEqual(
            listener._webhook_update_kind("[ORCHESTRATOR - MEDIUM LOCAL REVIEW] Model: gemma4:latest\n1. Cause"),
            "medium_review_done",
        )
        self.assertIn(
            "Ignored: Explain",
            listener._blocked_during_medium_review_message("!explain", []),
        )

    def test_status_reflects_failed_validation_and_resume_next_action(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._create_project_db(Path(temp_dir))
            response = listener.handle_command("!status", [], str(db_path))

            self.assertIn("Task 38", response)
            self.assertIn("Failed", response)
            self.assertIn("Resume", response)

    def test_task_run_card_payload_collapses_timeline_and_formats_env_failure(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._create_project_db(Path(temp_dir))
            for event_type, status, summary in [
                ("resume_received", "resuming", "Resume selected."),
                ("resume_received", "resuming", "Resume selected again."),
                ("validating", "validating", "Running deterministic validation."),
                ("validation_failed", "failed", "Forbidden path modified: .env"),
                ("paused", "paused", "Loop paused after failed validation."),
            ]:
                listener.operator_events.record_event(
                    db_path,
                    event_type,
                    task_id=38,
                    phase="Phase 10 - AI router and cost controls",
                    title="Implement AI router core",
                    status=status,
                    summary=summary,
                )

            payload = listener._task_run_card_payload(str(db_path))

            self.assertIn("Resume selected x2", str(payload["progress"]))
            self.assertIn("**Paused**", str(payload["progress"]))
            self.assertIn("`.env`", str(payload["finding"]))
            self.assertIn("deterministic validator", str(payload["finding"]))
            self.assertIn("press Resume", str(payload["next"]))

    def test_task_run_card_payload_caps_long_fields(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._create_project_db(Path(temp_dir))
            listener.operator_events.record_event(
                db_path,
                "validation_failed",
                task_id=38,
                phase="Phase 10 - AI router and cost controls",
                title="Implement AI router core",
                status="failed",
                summary="x" * 2000,
            )

            payload = listener._task_run_card_payload(str(db_path))

            self.assertLessEqual(len(str(payload["finding"])), listener.CARD_FIELD_LIMIT)

    def test_button_followup_message_always_closes_deferred_interaction(self) -> None:
        listener = load_listener_module()

        self.assertEqual(
            listener._button_followup_message("!resume", "Orchestrator resumed."),
            "Updated task card.",
        )
        self.assertIn(
            "What happened",
            listener._button_followup_message("!explain", "What happened:\nValidation failed."),
        )
        self.assertEqual(
            listener._button_followup_message("!wat", listener.UNKNOWN_COMMAND_MESSAGE),
            listener.UNKNOWN_COMMAND_MESSAGE,
        )

    def test_button_actions_reflect_pause_and_pending_approval(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._create_project_db(Path(temp_dir))
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    """
                    INSERT INTO approvals (
                        gate_type,
                        ref,
                        requested_at,
                        decision,
                        notes
                    ) VALUES ('Phase transition', 'phase-10-exit', '2026-05-09T10:00:00', NULL, 'pending')
                    """
                )
                connection.commit()
            finally:
                connection.close()

            actions = listener._button_actions_for_state(str(db_path))

            labels = [str(action["label"]) for action in actions]
            self.assertIn("Status", labels)
            self.assertIn("Explain", labels)
            self.assertIn("Resume", labels)
            self.assertIn("Approve phase-10-exit", labels)
            self.assertIn("Reject phase-10-exit", labels)

            listener.handle_command("!approve", ["phase-10-exit"], str(db_path))
            labels_after_approval = [
                str(action["label"]) for action in listener._button_actions_for_state(str(db_path))
            ]
            self.assertNotIn("Approve phase-10-exit", labels_after_approval)
            self.assertNotIn("Reject phase-10-exit", labels_after_approval)

    def test_button_actions_offer_pause_when_running(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._create_project_db(Path(temp_dir))
            connection = sqlite3.connect(db_path)
            try:
                connection.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES ('paused', '0')"
                )
                connection.commit()
            finally:
                connection.close()

            labels = [str(action["label"]) for action in listener._button_actions_for_state(str(db_path))]

            self.assertIn("Pause", labels)
            self.assertNotIn("Resume", labels)

    def test_in_flight_medium_review_hides_buttons_and_blocks_explain_model_call(self) -> None:
        listener = load_listener_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = self._create_project_db(Path(temp_dir))
            listener.operator_events.record_event(
                db_path,
                "medium_review_running",
                task_id=38,
                phase="Phase 10 - AI router and cost controls",
                title="Implement AI router core",
                status="reviewing",
                summary="Running medium local review with gemma4:latest.",
            )
            old_run_model_prompt = listener.prompt_runner.run_model_prompt
            try:
                listener.prompt_runner.run_model_prompt = lambda *args: self.fail(
                    "!explain should not call the low model during medium review"
                )

                actions = listener._button_actions_for_state(str(db_path))
                response = listener.handle_command("!explain", [], str(db_path))
                card = listener._task_run_card(str(db_path))
            finally:
                listener.prompt_runner.run_model_prompt = old_run_model_prompt

            self.assertEqual(actions, [])
            self.assertIn("Explain is unavailable", response)
            self.assertIn("Reviewing diagnosis", card)
            self.assertIn("Wait for the medium review result", card)

    def test_unknown_command_help_includes_explain(self) -> None:
        listener = load_listener_module()
        self.assertIn("!explain", listener.UNKNOWN_COMMAND_MESSAGE)


if __name__ == "__main__":
    unittest.main()
