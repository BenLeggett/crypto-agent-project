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


if __name__ == "__main__":
    unittest.main()
