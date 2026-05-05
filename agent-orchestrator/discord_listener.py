from __future__ import annotations

import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv


DEFAULT_DB_PATH = str(Path(__file__).with_name("state.sqlite"))
MOCK_MODE_MESSAGE = "Running in mock mode \u2014 bot token not configured"
UNKNOWN_COMMAND_MESSAGE = (
    "Unknown command. Available: !status !approve !reject !pause !resume"
)
COMMAND_ALIASES = {
    "!reusme": "!resume",
}


def _load_local_env() -> None:
    """Load the orchestrator-local .env file when present."""
    load_dotenv(Path(__file__).with_name(".env"))


def _connect(db_path: str) -> sqlite3.Connection:
    """Open the SQLite database and ensure listener-owned tables exist."""
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute(
        "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
    )
    return connection


def _now_timestamp() -> str:
    """Return a stable wall-clock timestamp for SQLite inserts."""
    return datetime.now().isoformat(timespec="seconds")


def _normalize_status(status: str | None) -> str:
    """Convert a task status into a Discord-friendly label."""
    if not status:
        return "unknown"
    return status.replace("_", " ")


def _format_status_message(
    phase: str,
    task_id: str | int,
    task_title: str,
    task_status: str | None,
) -> str:
    """Return the status update format defined in the plan doc."""
    human_status = _normalize_status(task_status)
    return (
        f"[ORCHESTRATOR] {phase} \u00b7 Task {task_id}: {task_title}\n"
        f"Status: {human_status}\n"
        "Model used: n/a\n"
        "Validation: pending\n"
        "Next: wait for the orchestrator to process this task"
    )


def _read_status(connection: sqlite3.Connection) -> str:
    """Read the current phase and first pending task from the tasks table."""
    current_row = connection.execute(
        """
        SELECT task_id, phase, title, status
        FROM tasks
        WHERE status NOT IN ('done', 'skipped')
        ORDER BY
            CASE status WHEN 'in_progress' THEN 0 WHEN 'pending' THEN 1 ELSE 2 END,
            phase,
            task_id
        LIMIT 1
        """
    ).fetchone()

    if current_row is None:
        return (
            "[ORCHESTRATOR] No active phase \u00b7 Task n/a: No pending tasks\n"
            "Status: idle\n"
            "Model used: n/a\n"
            "Validation: n/a\n"
            "Next: queue a task or advance the phase"
        )

    pending_row = connection.execute(
        """
        SELECT task_id, phase, title, status
        FROM tasks
        WHERE phase = ? AND status = 'pending'
        ORDER BY task_id
        LIMIT 1
        """,
        (current_row["phase"],),
    ).fetchone()

    task_row = pending_row or current_row
    return _format_status_message(
        phase=str(current_row["phase"]),
        task_id=task_row["task_id"],
        task_title=str(task_row["title"]),
        task_status=task_row["status"],
    )


def _record_approval(
    connection: sqlite3.Connection,
    ref: str,
    decision: str,
    notes: str | None = None,
) -> None:
    """Insert a decision record into the approvals table."""
    connection.execute(
        """
        INSERT INTO approvals (ref, decision, notes, decided_at)
        VALUES (?, ?, ?, ?)
        """,
        (ref, decision, notes, _now_timestamp()),
    )
    connection.commit()


def _set_paused(connection: sqlite3.Connection, paused: bool) -> None:
    """Persist the orchestrator pause flag in the settings table."""
    connection.execute(
        """
        INSERT OR REPLACE INTO settings (key, value)
        VALUES ('paused', ?)
        """,
        ("1" if paused else "0",),
    )
    connection.commit()


def handle_command(command: str, args: list[str], db_path: str) -> str:
    """Parse and execute a supported Discord command."""
    try:
        with closing(_connect(db_path)) as connection:
            if command == "!status":
                return _read_status(connection)

            if command == "!approve":
                if not args:
                    return "Usage: !approve <ref>"
                ref = args[0]
                _record_approval(connection, ref=ref, decision="approved")
                return f"Approved: {ref}"

            if command == "!reject":
                if len(args) < 2:
                    return "Usage: !reject <ref> <notes>"
                ref = args[0]
                notes = " ".join(args[1:]).strip()
                _record_approval(
                    connection,
                    ref=ref,
                    decision="rejected",
                    notes=notes,
                )
                return f"Rejected: {ref} \u2014 {notes}"

            if command == "!pause":
                _set_paused(connection, paused=True)
                return "Orchestrator paused. Send !resume to continue."

            if command == "!resume":
                _set_paused(connection, paused=False)
                return "Orchestrator resumed."
    except sqlite3.Error as exc:
        return f"Database error: {exc}"

    return UNKNOWN_COMMAND_MESSAGE


def _parse_command_line(line: str) -> tuple[str, list[str]] | None:
    """Split a raw line into the command token and its arguments."""
    stripped = line.strip()
    if not stripped or not stripped.startswith("!"):
        return None

    parts = stripped.split()
    command = parts[0].lower()
    command = COMMAND_ALIASES.get(command, command)
    return command, parts[1:]


def _resolve_db_path() -> str:
    """Resolve the database path from the environment or fallback."""
    return (os.getenv("DB_PATH") or DEFAULT_DB_PATH).strip() or DEFAULT_DB_PATH


def _log_stderr(prefix: str, message: str) -> None:
    """Write operational logs to stderr for service visibility."""
    print(f"[DISCORD-LISTENER] {prefix}: {message}", file=sys.stderr)


def _run_mock_mode(db_path: str) -> None:
    """Run a local stdin loop for testing without a Discord bot token."""
    print(MOCK_MODE_MESSAGE)
    for raw_line in sys.stdin:
        parsed = _parse_command_line(raw_line)
        if parsed is None:
            continue

        command, args = parsed
        _log_stderr("command", raw_line.strip())
        response = handle_command(command, args, db_path)
        _log_stderr("response", response)
        print(response)


def _run_discord_mode(bot_token: str, channel_id: int, db_path: str) -> None:
    """Run the real Discord listener scoped to one command channel."""
    import discord

    intents = discord.Intents.default()
    intents.message_content = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        _log_stderr("ready", f"connected as {client.user}")

    @client.event
    async def on_message(message) -> None:
        if message.author == client.user:
            return
        if message.channel.id != channel_id:
            return

        parsed = _parse_command_line(message.content)
        if parsed is None:
            return

        command, args = parsed
        _log_stderr("command", message.content.strip())
        response = handle_command(command, args, db_path)
        _log_stderr("response", response)
        await message.channel.send(response)

    client.run(bot_token)


def main() -> None:
    """Start either mock mode or the real Discord listener."""
    _load_local_env()
    db_path = _resolve_db_path()
    bot_token = (os.getenv("DISCORD_BOT_TOKEN") or "").strip()

    if not bot_token:
        _run_mock_mode(db_path)
        return

    channel_id_raw = (os.getenv("DISCORD_COMMAND_CHANNEL_ID") or "").strip()
    if not channel_id_raw:
        raise SystemExit("DISCORD_COMMAND_CHANNEL_ID is required when DISCORD_BOT_TOKEN is set.")

    try:
        channel_id = int(channel_id_raw)
    except ValueError as exc:
        raise SystemExit("DISCORD_COMMAND_CHANNEL_ID must be an integer.") from exc

    _run_discord_mode(bot_token, channel_id, db_path)


if __name__ == "__main__":
    main()
