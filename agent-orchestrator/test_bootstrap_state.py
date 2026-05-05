from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path


TEST_ROOT = Path(__file__).resolve().parent
if str(TEST_ROOT) not in sys.path:
    sys.path.insert(0, str(TEST_ROOT))

import bootstrap_state


class BootstrapStateTests(unittest.TestCase):
    def test_seed_tasks_adds_pending_rows_and_preserves_done_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            queue_path = temp_path / "TASK_QUEUE.md"
            phase_map_path = temp_path / "PHASE_TASK_MAP.md"
            db_path = temp_path / "state.sqlite"

            queue_path.write_text(
                "\n".join(
                    [
                        "# Task Queue",
                        "",
                        "## 1. First task",
                        "- Goal: one",
                        "- Files likely affected: `one.py`",
                        "- Dependencies: none",
                        "- Done criteria: first done",
                        "",
                        "## 2. Second task",
                        "- Goal: two",
                        "- Files likely affected: `two.py`",
                        "- Dependencies: 1",
                        "- Done criteria: second done",
                        "",
                        "## 3. Third task",
                        "- Goal: three",
                        "- Files likely affected: `three.py`",
                        "- Dependencies: 2",
                        "- Done criteria: third done",
                    ]
                ),
                encoding="utf-8",
            )
            phase_map_path.write_text(
                "\n".join(
                    [
                        "## Phase 1 - Example phase",
                        "",
                        "### Primary tasks",
                        "- 1. First task",
                        "- 2. Second task",
                        "- 3. Third task",
                    ]
                ),
                encoding="utf-8",
            )

            bootstrap_state.init_tasks_table(db_path)
            phases = bootstrap_state.parse_phase_task_map(phase_map_path)

            bootstrap_state.seed_tasks(phases, queue_path, db_path)
            bootstrap_state.mark_done([1, 3], phases, queue_path, db_path)
            bootstrap_state.seed_tasks(phases, queue_path, db_path)

            connection = sqlite3.connect(db_path)
            try:
                rows = connection.execute(
                    "SELECT task_id, phase, title, status FROM tasks ORDER BY task_id"
                ).fetchall()
            finally:
                connection.close()

            self.assertEqual(
                rows,
                [
                    (1, "Phase 1 - Example phase", "First task", "done"),
                    (2, "Phase 1 - Example phase", "Second task", "pending"),
                    (3, "Phase 1 - Example phase", "Third task", "done"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
