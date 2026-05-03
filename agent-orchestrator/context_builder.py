from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from task_queue_reader import read_task


MAX_CONTEXT_TOKENS = int(os.getenv("ORCHESTRATOR_MAX_CONTEXT_TOKENS", "4096"))


def estimate_tokens(text: str) -> int:
    """Estimate token usage from whitespace-delimited words."""
    return int(len(text.split()) * 1.3)


def _resolve_paths(project_root: str) -> tuple[Path, Path]:
    root = Path(project_root).resolve()
    if root.name == "agent-orchestrator":
        return root.parent, root
    return root, root / "agent-orchestrator"


def _trim_to_tokens(text: str, max_tokens: int, label: str) -> str:
    if estimate_tokens(text) <= max_tokens:
        return text
    max_words = max(1, int(max_tokens / 1.3))
    logging.warning("Truncated %s to %s estimated tokens.", label, max_tokens)
    return " ".join(text.split()[:max_words])


def _read_file_section(path: Path, max_tokens: int, label: str) -> str:
    text = path.read_text(encoding="utf-8")
    return _trim_to_tokens(text, max_tokens, label)


def _format_task(task: dict) -> str:
    files = ", ".join(task["files"]) if task["files"] else "none"
    dependencies = ", ".join(str(item) for item in task["dependencies"]) or "none"
    return "\n".join(
        [
            f"Task {task['id']}: {task['title']}",
            f"Goal: {task['goal']}",
            f"Files likely affected: {files}",
            f"Dependencies: {dependencies}",
            f"Done criteria: {task['done_criteria']}",
        ]
    )


def _read_activity_tail(project_root: Path) -> str:
    path = project_root / "ACTIVITY.MD"
    if not path.exists():
        return ""
    return "\n".join(path.read_text(encoding="utf-8").splitlines()[-5:])


def _read_diff_stat(project_root: Path) -> str:
    result = subprocess.run(
        ["git", "diff", "--stat", "HEAD"],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    return (result.stdout + result.stderr).strip()


def build_context(task_id: str, project_root: str, include_diff: bool = False) -> str:
    """Build a compact context pack for a task."""
    root, orchestrator_root = _resolve_paths(project_root)
    queue_path = root / "docs" / "TASK_QUEUE.md"

    section_specs: list[tuple[str, str, int]] = [
        (
            "Project summary",
            _read_file_section(orchestrator_root / "context" / "project_summary.md", 300, "project summary"),
            300,
        ),
        (
            "Current phase",
            _read_file_section(orchestrator_root / "context" / "current_phase.md", 200, "current phase"),
            200,
        ),
        (
            "Architecture rules",
            _read_file_section(orchestrator_root / "context" / "architecture_rules.md", 300, "architecture rules"),
            300,
        ),
        (
            "Task",
            _trim_to_tokens(_format_task(read_task(task_id, str(queue_path))), 400, "task"),
            400,
        ),
    ]

    activity_tail = _read_activity_tail(root)
    if activity_tail:
        section_specs.append(("Recent activity", _trim_to_tokens(activity_tail, 300, "recent activity"), 300))

    if include_diff:
        diff_stat = _read_diff_stat(root)
        if diff_stat:
            section_specs.append(("Diff stat", _trim_to_tokens(diff_stat, 200, "diff stat"), 200))

    sections: list[str] = []
    used_tokens = 0
    for title, content, section_limit in section_specs:
        remaining = MAX_CONTEXT_TOKENS - used_tokens
        if remaining <= 0:
            logging.warning("Context budget exhausted before adding %s.", title)
            break
        clipped = _trim_to_tokens(content, min(section_limit, remaining), title)
        sections.append(f"{title}\n{clipped}")
        used_tokens += estimate_tokens(clipped)

    return "\n---\n".join(sections)
