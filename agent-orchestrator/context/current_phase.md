Current phase: Agent Orchestrator Bootstrap — Practical Setup and Read-Only Foundation

Active task ID: AO-001

Active task: Establish the initial local development orchestrator scaffold and verify the basic external plumbing.

Current known completed setup:
- Python virtual environment has already been created.
- Discord webhook has already been confirmed working through `test_discord.py`.

Current focus:
- Create and populate the required context files:
  - `agent-orchestrator/context/project_summary.md`
  - `agent-orchestrator/context/current_phase.md`
  - `agent-orchestrator/context/architecture_rules.md`
- Keep the orchestrator in read-only/manual mode.
- Do not enable automatic Codex execution.
- Do not add two-way Discord bot command handling yet.
- Do not implement trading-bot operations logic.

Exit criteria:
- `agent-orchestrator/context/` contains the three required context files.
- `.env` exists locally and includes the confirmed Discord webhook URL.
- The orchestrator can run its first read-only status flow without touching trading runtime code.
- Discord status posting works through the webhook.
- No files under live config, exchange credentials, trading execution, or risk-sensitive runtime paths are modified.
- The next implementation step can proceed to Stage 1/Stage 5-style scaffold and `--status` command work using Codex.
