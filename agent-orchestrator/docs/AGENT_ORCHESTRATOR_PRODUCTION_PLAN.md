# `docs/AGENT_ORCHESTRATOR_PRODUCTION_PLAN.md`

> **Scope:** Supplementary to `AGENT_ORCHESTRATOR_PLAN.md`. Covers the four additional stages required to reach a fully autonomous production setup: Discord bot listener, autonomous task loop, Ollama swap, and Mode B hardening. Also defines the testing protocol at each critical junction.
>
> **Platform:** Windows (production machine). Stage 12c service setup uses NSSM or Task Scheduler. Ollama installs as a Windows service automatically.
>
> **Read `AGENT_ORCHESTRATOR_PLAN.md` first.** This document assumes Stages 1–11 are complete and verified.

---

## Overview: the production sequencing

```
[Stages 1–11 complete]
        ↓
Junction A: Full Mode A end-to-end verification
        ↓
Stage 12a: Discord listener bot
        ↓
Stage 12b: Autonomous task loop (--run-loop, Mode A)
        ↓
Junction B: Full loop verification in Mode A
        ↓
Stage 12c: Ollama swap (production machine)
        ↓
Junction C: Headless local LLM verification
        ↓
Stage 12d: Mode B hardening (Codex CLI automation)
        ↓
Junction D: Full Mode B end-to-end verification
        ↓
[Production: unsupervised run-loop with Discord control]
```

Each junction is a mandatory hold point. Do not proceed past a junction until all its checks pass.

---

## Junction A — Full Mode A end-to-end verification

**When:** After Stages 1–11 are complete. Before writing any new code.

**What you are verifying:** The entire manual flow works correctly as a complete cycle, not just individual stages in isolation.

**Run this sequence in order:**

```bash
# 1. Confirm status reads correctly
python orchestrator.py --status
# Expected: current phase name, active task ID and title, done criteria

# 2. Confirm prompt assembly
python orchestrator.py --run-next
# Expected: "Prompt written to last_prompt.md" + first 20 lines of the prompt
# Open last_prompt.md and confirm: task context is injected, template is complete

# 3. Simulate applying a task (make a trivial safe change in the repo, e.g. add a comment)
# Then run validation
python orchestrator.py --validate
# Expected: passed: True, no errors, diff summary shows your trivial change

# 4. Confirm activity logging
cat ../ACTIVITY.md
# Expected: at least one formatted entry from the validation run

# 5. Confirm Discord outbound
# Run --run-next again and check that a status message appears in your Discord channel

# 6. Confirm phase review flow (does NOT need to complete — just confirm it starts)
python orchestrator.py --phase-review
# Expected: context is built, cloud_high model is called, result posted to Discord
# You should see an approval request message in Discord
# Ctrl+C to exit without approving — that is fine for this check

# 7. Check decision_log.md has an entry even for the incomplete run
cat agent-orchestrator/context/decision_log.md
```

**Junction A pass criteria:**

- [ ] `--status` shows real task data from `TASK_QUEUE.md`
- [ ] `--run-next` writes a complete, correctly injected `last_prompt.md`
- [ ] `--validate` passes on a clean repo and catches a deliberate forbidden path change
- [ ] `ACTIVITY.md` receives entries from each command
- [ ] Discord receives outbound messages for status and phase review
- [ ] `decision_log.md` is written to

**Do not proceed to Stage 12a until all six pass.**

---

## Stage 12a — Discord listener bot

### Objective

Add a persistent bot process (`discord_listener.py`) that receives inbound Discord commands and writes decisions to `state.sqlite`. This is what allows you to approve phases, request status, and pause/resume the orchestrator from your phone.

### New files

```
agent-orchestrator/
└── discord_listener.py    # persistent bot process
```

### New dependency

```bash
pip install discord.py
```

Add to `requirements.txt` or document in `README.md`.

### New manual wiring requirement

A Discord **bot token** is required — distinct from the webhook URL. Add to `MANUAL_WIRING_CHECKLIST.md`:

```
### Item
- Status: pending
- Area: Discord bot token (inbound command listener)
- Reason human input is required: Bot tokens are user-owned secrets created via Discord Developer Portal
- File(s): .env, agent-orchestrator/discord_listener.py
- Env var(s): DISCORD_BOT_TOKEN, DISCORD_COMMAND_CHANNEL_ID
- Expected format: Discord bot token string; channel ID as integer string
- Placeholder or mock already implemented: listener prints commands to stdout if token missing
- Validation / failure behavior if missing: listener starts in mock mode, logs commands locally only
- Manual steps for human:
    1. Go to discord.com/developers/applications
    2. Create a new application → Bot → copy token
    3. Enable MESSAGE CONTENT intent under Bot settings
    4. Invite bot to server with permissions: Read Messages, Send Messages
    5. Copy the command channel ID (right-click channel → Copy Channel ID)
    6. Add DISCORD_BOT_TOKEN and DISCORD_COMMAND_CHANNEL_ID to .env
- Verification steps after wiring: run discord_listener.py, send !status in channel, confirm response
- Notes: Keep bot token secret. Never commit to repo.
```

### Codex prompt

```
Read docs/AGENT_ORCHESTRATOR_PLAN.md and docs/AGENT_ORCHESTRATOR_PRODUCTION_PLAN.md first.

I am implementing Stage 12a: Discord listener bot.

New file to create: agent-orchestrator/discord_listener.py
Files to inspect: agent-orchestrator/state.sqlite schema (from AGENT_ORCHESTRATOR_PLAN.md §11),
                  agent-orchestrator/discord_notifier.py
All other files are off-limits.

Implement discord_listener.py as follows:

1. Load environment via python-dotenv:
   - DISCORD_BOT_TOKEN (required for real mode)
   - DISCORD_COMMAND_CHANNEL_ID (required for real mode)
   - DB_PATH (default: agent-orchestrator/state.sqlite)

2. Define handle_command(command: str, args: list[str], db_path: str) -> str
   Parses and acts on these commands, returning a response string:

   !status
     → Read state.sqlite tasks table for current phase and first pending task
     → Return formatted status string matching AGENT_ORCHESTRATOR_PLAN.md §8 message format

   !approve <ref>
     → INSERT into approvals table: ref=ref, decision="approved", decided_at=now
     → Return "Approved: {ref}"

   !reject <ref> <notes...>
     → INSERT into approvals table: ref=ref, decision="rejected", notes=joined notes, decided_at=now
     → Return "Rejected: {ref} — {notes}"

   !pause
     → INSERT OR REPLACE into a settings table (key="paused", value="1")
     → Return "Orchestrator paused. Send !resume to continue."

   !resume
     → INSERT OR REPLACE into settings table (key="paused", value="0")
     → Return "Orchestrator resumed."

   Unrecognized command:
     → Return "Unknown command. Available: !status !approve !reject !pause !resume"

3. Initialize state.sqlite with a settings table if not present:
   CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)

4. If DISCORD_BOT_TOKEN is set:
   - Use discord.py Client to connect
   - Listen for messages in DISCORD_COMMAND_CHANNEL_ID only
   - On each message starting with "!": parse command and args, call handle_command(), 
     send response back to same channel
   - Log every command received and response sent to stderr

5. If DISCORD_BOT_TOKEN is not set (mock mode):
   - Print "Running in mock mode — bot token not configured"
   - Start a stdin loop: read lines, parse as commands, call handle_command(), print response
   - This allows local testing without a real bot token

6. __main__ entry point runs the appropriate mode.

Use only: discord.py, sqlite3, standard library, python-dotenv.
Do NOT modify any other file.
Do NOT import from apps/, libs/, or freqtrade/.
```

### Verification after Stage 12a

**Mock mode test (no bot token needed):**
```bash
cd agent-orchestrator
python discord_listener.py
# Type: !status
# Expected: formatted status output
# Type: !approve test-ref-001
# Expected: "Approved: test-ref-001"
# Check state.sqlite approvals table has the row:
python -c "import sqlite3; c=sqlite3.connect('state.sqlite'); print(c.execute('SELECT * FROM approvals').fetchall())"
```

**Real bot test (after wiring token):**
1. Run `python discord_listener.py` in a terminal.
2. Send `!status` in your Discord channel.
3. Confirm the bot responds in the channel within a few seconds.
4. Send `!approve junction-a-test`.
5. Confirm `state.sqlite` approvals table has the row.
6. Send `!pause` then `!resume` and confirm settings table updates.

---

## Stage 12b — Autonomous task loop

### Objective

Add `--run-loop` mode to `orchestrator.py`. This is the core production behaviour: the orchestrator runs tasks continuously, blocks at phase gates for human approval, pauses on failure, and resumes when instructed.

### How the loop works

```
loop start
  ↓
check settings.paused → if "1": sleep 30s, continue
  ↓
get next pending task for current phase
  ↓
if no pending tasks:
  trigger phase review (run_model_prompt with phase_review.md)
  post approval request to Discord
  insert pending approval into state.sqlite
  block: poll state.sqlite every 10s until approved/rejected/timeout
  if approved: advance phase, continue loop
  if rejected: post to Discord, set paused=1, exit loop
  ↓
if pending task exists:
  check risky gate (validator forbidden path pre-check on task's listed files)
  if risky:
    post approval request to Discord
    block until approved (same polling pattern)
    if rejected: log, continue to next task
  ↓
  assemble_prompt() → last_prompt.md
  post to Discord: "Running task N: {title}"
  [Mode A: post prompt to Discord, set paused=1, keep loop alive — human applies manually]
  [Mode B: invoke Codex CLI, capture output]
  ↓
  run validator.validate()
  if failed:
    post failure to Discord with error summary
    set paused=1
    log activity with outcome=failed
    exit loop (human must !resume after fixing)
  if passed:
    mark task done in state.sqlite
    log activity with outcome=passed
    post success to Discord
    sleep(LOOP_INTERVAL_SECONDS)
    continue loop
```

### New env variable

```dotenv
LOOP_INTERVAL_SECONDS=30     # pause between tasks in run-loop mode
CODEX_MODE=manual            # manual | auto — controls Mode A vs B behaviour in loop
LOCAL_VALIDATION_SUMMARY=failures_only  # failures_only | always | off; advisory local diagnostics
LOCAL_LLM_LOW_TIMEOUT_SECONDS=30        # routine low local model timeout
LOCAL_LLM_LOW_MAX_TOKENS=256            # routine low local model output cap
LOCAL_LLM_LOW_KEEP_ALIVE=30m            # Ollama residency request for low local calls
LOCAL_LLM_MEDIUM_WARMUP_TIMEOUT_SECONDS=120 # medium model cold-start warmup timeout
LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS=180    # validation failure review timeout
LOCAL_LLM_MEDIUM_MAX_TOKENS=600         # validation failure review output cap
LOCAL_LLM_MEDIUM_KEEP_ALIVE=60m         # Ollama residency request for medium local calls
LOCAL_LLM_PRELOAD_ON_START=true         # warm low model when Discord listener starts
LOCAL_LLM_PRELOAD_MEDIUM_ON_START=true  # warm medium model on listener startup, best effort
LOCAL_LLM_UNLOAD_MEDIUM_AFTER_REVIEW=false # optional best-effort Ollama unload
LOCAL_LLM_RETRY_ATTEMPTS=2              # retry local model startup/connection hiccups
LOCAL_LLM_RETRY_BACKOFF_SECONDS=1       # local model retry delay baseline
DISCORD_WEBHOOK_RETRY_ATTEMPTS=3        # retry transient Discord webhook 429/5xx responses
DISCORD_WEBHOOK_RETRY_BACKOFF_SECONDS=1 # Discord webhook retry delay baseline
```

### Local diagnostics and operator explanation

Validation remains deterministic and model-free. When validation fails, the
run-loop immediately marks the task `failed`, records `validation_failed`, sets
`paused=1`, and restores idle card controls. The Discord listener then rebuilds
compact failure context from SQLite/activity and runs a low-model diagnosis in
the background. Medium diagnosis is explicit only: the `Deep Diagnose` button
records `medium_review_running`, hides buttons, blocks `!explain`, and runs the
medium review asynchronously. The context is compact: task id/title, validator
error/warning summary, task notes, and recent `ACTIVITY.MD` entries. It does not
include `.env`, secrets, live config paths, full file contents, or full git
patches. If either model is unavailable or times out, the task still remains
`failed`, `paused=1` remains set, and the card records an unavailable diagnosis
with the underlying connection/timeout/status detail when available.

The Discord listener also supports read-only `!explain`. It must not mutate task
rows, settings, approvals, prompt files, phase state, or approval state. It uses
`prompts/latest_action_explain.md` with `LOCAL_LOW` over compact SQLite
status, paused state, latest advisory diagnosis, recent activity, and a prompt
excerpt. It intentionally does not include git diff summaries so operator
context stays compact. If the local model fails, it returns a deterministic
explanation from SQLite status and recent activity plus the local model failure
reason.

In Discord mode, the listener renders one evolving task run card from durable
`operator_events` in `state.sqlite`. The card shows the active task, compact
timeline, current state, latest finding, and next action; buttons attach only
when the card is idle. In Discord mode the card is an embed with separate fields,
collapsed repeated timeline steps, capped text lengths, and operator-friendly
wording for deterministic failures such as forbidden `.env` edits. Button
callbacks always send a followup after deferring so Discord's native thinking
indicator clears after the card update. Routine run-loop transitions such as
prompt-ready, resume, validating, validation failed, low diagnosis done,
medium-review running, medium-review done, paused, task-done, and model preload
readiness are SQLite events rather than public webhook spam. During validation
or explicit medium review, buttons are removed and
Discord's typing indicator shows that the system is working. `!explain` is
blocked while review is in flight so the low model does not compete with the
medium diagnostic call. When the listener restarts, it recovers or recreates the
task card from SQLite. Webhook parsing remains only as compatibility fallback
for older notifications or emergency messages.

### Codex prompt

```
Read docs/AGENT_ORCHESTRATOR_PLAN.md and docs/AGENT_ORCHESTRATOR_PRODUCTION_PLAN.md first.

I am implementing Stage 12b: autonomous task loop.

File to modify: agent-orchestrator/orchestrator.py
Files to inspect: agent-orchestrator/prompt_runner.py, agent-orchestrator/validator.py,
                  agent-orchestrator/discord_notifier.py, agent-orchestrator/decision_gate.py,
                  agent-orchestrator/activity_logger.py, agent-orchestrator/task_queue_reader.py
All other files are off-limits.

Add --run-loop flag to orchestrator.py implementing this behaviour:

1. On start: log "Starting run loop" to ACTIVITY.md and post to Discord

2. Main loop (infinite, exit only on rejection or unrecoverable error):

   a. Check settings table in state.sqlite for paused="1"
      If paused: sleep LOOP_INTERVAL_SECONDS, continue

   b. Get next pending task using task_queue_reader
      If no pending tasks in current phase:
        - Call prompt_runner.run_model_prompt with phase_review.md and CLOUD_HIGH
        - Post result to Discord as approval request with ref "phase-{N}-exit"
        - Call decision_gate.wait_for_approval("phase-{N}-exit")
        - If approved: update current phase in state.sqlite, log activity, continue
        - If rejected or timeout: post to Discord, set paused=1, break loop

   c. Check risky gate: does task's file list overlap FORBIDDEN_PATHS or risky dirs?
      If risky:
        - Post approval request to Discord with ref "task-{id}-risky"
        - Call decision_gate.wait_for_approval("task-{id}-risky")
        - If rejected: log, skip task (mark skipped), continue loop

   d. Call prompt_runner.assemble_prompt() → last_prompt.md

   e. Read CODEX_MODE from env:
      If "manual":
        - Post last_prompt.md content (or link) to Discord
        - Post: "Manual mode: apply the prompt in last_prompt.md, then send !resume"
        - Set paused=1 in settings table
        - Continue sleeping in the live loop until the human resumes after applying
      If "auto":
        - Post: "Running Codex on task {id}: {title}"
        - subprocess.run(["codex", "run", "--prompt-file", "agent-orchestrator/last_prompt.md"])
        - Capture return code

   f. Run validator.validate(project_root)
      If failed:
        - Post failure notification to Discord with error list
        - Log activity with outcome="failed"
        - Set paused=1
        - Break loop
      If passed:
        - Mark task done in state.sqlite
        - Log activity with outcome="passed"
        - Post success to Discord: "Task {id} complete ✅"
        - sleep(LOOP_INTERVAL_SECONDS)
        - Continue loop

3. On any unhandled exception: post error to Discord, log to ACTIVITY.md, exit 1

Do NOT remove or modify existing --status, --run-next, --phase-review, --validate commands.
Do NOT modify any other file.
```

### Verification after Stage 12b

Run the loop in **manual mode** (safe — it will pause after each task and wait for you):

```bash
# Terminal 1: listener
python discord_listener.py

# Terminal 2: orchestrator loop
CODEX_MODE=manual python orchestrator.py --run-loop
```

Expected sequence:
1. "Starting run loop" appears in Discord
2. Orchestrator assembles prompt for current task
3. Discord receives: "Manual mode: apply the prompt in last_prompt.md, then send !resume"
4. Orchestrator pauses
5. You send `!resume` in Discord
6. Listener writes `paused=0` to `state.sqlite`
7. Orchestrator wakes, runs validator, posts result
8. Cycle repeats for next task

Verify each step happens before moving on.

---

## Junction B — Full loop verification in Mode A

**When:** After Stages 12a and 12b are complete.

**What you are verifying:** The two-process system (orchestrator loop + Discord listener) works correctly together through at least one complete task cycle and one complete phase transition.

**Run this full scenario:**

```bash
# Terminal 1
python discord_listener.py

# Terminal 2
CODEX_MODE=manual python orchestrator.py --run-loop
```

**Scenario to run through:**

1. Orchestrator starts → confirm Discord message received
2. First task prompt assembled → confirm Discord message received
3. Send `!status` from Discord → confirm bot responds with current state
4. Apply the prompt manually to your project (do actual work)
5. Send `!resume` → confirm orchestrator wakes
6. Validator runs → confirm pass message in Discord and `ACTIVITY.md` entry
7. Repeat for remaining tasks in current phase until phase gate triggers
8. Phase review posts to Discord → confirm approval request received
9. Send `!approve phase-{N}-exit` → confirm orchestrator advances phase
10. New phase starts → confirm Discord message with new phase name
11. Send `!pause` → confirm loop pauses
12. Send `!resume` → confirm loop resumes

**Junction B pass criteria:**

- [ ] Both processes run stably together without errors
- [ ] `!status` returns accurate current state from Discord
- [ ] `!pause` and `!resume` reliably control the loop
- [ ] Phase gate correctly blocks until `!approve` received
- [ ] `!approve` unblocks the loop within one polling interval (≤10 seconds)
- [ ] `ACTIVITY.md` has entries for every step
- [ ] `context/decision_log.md` has the phase approval entry
- [ ] No messages sent to wrong channel or double-posted

**Do not proceed to Stage 12c until all pass.**

---

## Stage 12c — Ollama swap (Windows)

### Objective

Replace LM Studio with Ollama on the Windows machine that will run the orchestrator in production. Ollama installs as a Windows service automatically, has no GUI dependency, and survives reboots — making it suitable for unsupervised operation. No code changes required; this is configuration and documentation only.

### Installation

```powershell
# 1. Download and run the Ollama installer from https://ollama.ai/download
#    The installer registers Ollama as a Windows service automatically.
#    Default port: 11434

# 2. Open a new terminal after install and pull your models
ollama pull mistral        # local_low equivalent
ollama pull llama3.1       # local_medium equivalent

# 3. Verify the API is reachable
curl http://localhost:11434/v1/models
# Expected: JSON list of pulled models
```

Ollama registers itself as a Windows service named `ollama` that starts on boot by default. Confirm in Task Manager → Services tab → find `ollama` → Status should be Running.

### `.env` update

```dotenv
# Replace LM Studio values with Ollama
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_API_KEY=ollama       # Ollama ignores this but the client requires a value
LOCAL_LLM_LOW_MODEL=mistral
LOCAL_LLM_MEDIUM_MODEL=llama3.1
```

No changes to `local_llm_client.py` — Ollama exposes the same OpenAI-compatible API that LM Studio used. Only the URL and model names change.

### Making the orchestrator and listener start on boot (Windows)

Two options — choose one.

#### Option A: Task Scheduler (no extra tools needed)

For each process (`orchestrator.py --run-loop` and `discord_listener.py`), create a scheduled task:

1. Open **Task Scheduler** → **Create Task**
2. **General tab:**
   - Name: `OrchestratorLoop` (or `OrchestratorListener` for the second task)
   - Select: **Run whether user is logged on or not**
   - Select: **Run with highest privileges** (only if needed for file access)
3. **Triggers tab:** New → **At startup**
4. **Actions tab:** New → Start a program
   - Program/script: `C:\path\to\repo\agent-orchestrator\.venv\Scripts\python.exe`
   - Add arguments: `orchestrator.py --run-loop` (or `discord_listener.py`)
   - Start in: `C:\path\to\repo\agent-orchestrator`
5. **Settings tab:**
   - Check: **Restart if the task fails**, every 1 minute, up to 3 times
   - Check: **If the task is already running, do not start a new instance**

Repeat for `discord_listener.py` with name `OrchestratorListener`.

#### Option B: NSSM — Non-Sucking Service Manager (recommended)

NSSM wraps any executable as a proper Windows service with automatic restart and log capture. Closer equivalent to `systemd` on Linux.

```powershell
# Download nssm.exe from https://nssm.cc and place it on your PATH, then:

# Register orchestrator as a service
nssm install OrchestratorLoop "C:\path\to\repo\agent-orchestrator\.venv\Scripts\python.exe"
nssm set OrchestratorLoop AppParameters "orchestrator.py --run-loop"
nssm set OrchestratorLoop AppDirectory "C:\path\to\repo\agent-orchestrator"
nssm set OrchestratorLoop AppStdout "C:\path\to\repo\agent-orchestrator\logs\orchestrator.stdout.log"
nssm set OrchestratorLoop AppStderr "C:\path\to\repo\agent-orchestrator\logs\orchestrator.stderr.log"
nssm set OrchestratorLoop Start SERVICE_AUTO_START
nssm start OrchestratorLoop

# Register listener as a service
nssm install OrchestratorListener "C:\path\to\repo\agent-orchestrator\.venv\Scripts\python.exe"
nssm set OrchestratorListener AppParameters "discord_listener.py"
nssm set OrchestratorListener AppDirectory "C:\path\to\repo\agent-orchestrator"
nssm set OrchestratorListener AppStdout "C:\path\to\repo\agent-orchestrator\logs\listener.stdout.log"
nssm set OrchestratorListener AppStderr "C:\path\to\repo\agent-orchestrator\logs\listener.stderr.log"
nssm set OrchestratorListener Start SERVICE_AUTO_START
nssm start OrchestratorListener

# Verify both are running
nssm status OrchestratorLoop
nssm status OrchestratorListener
```

To stop, start, or restart later:
```powershell
nssm stop OrchestratorLoop
nssm restart OrchestratorLoop
```

NSSM is recommended over Task Scheduler because it handles log rotation, restart-on-crash, and service dependency ordering more reliably.

### Creating the logs directory

```powershell
mkdir C:\path\to\repo\agent-orchestrator\logs
```

Create this before starting the services — NSSM and Task Scheduler will fail silently if the log path does not exist.

### Verification after Stage 12c

```powershell
# 1. Confirm Ollama service is running
Get-Service -Name "ollama"
# Expected: Status = Running

# 2. Confirm API is reachable
curl http://localhost:11434/v1/models
# Expected: JSON list of your pulled models

# 3. Confirm local_llm_client works against Ollama
#    (with LM Studio closed — do not have both running simultaneously)
cd agent-orchestrator
python local_llm_client.py
# Expected: ping success, one-sentence hello from the Ollama model

# 4. Confirm orchestrator uses Ollama for prompt assembly
python orchestrator.py --run-next
# Expected: prompt assembled successfully, no LM Studio dependency

# 5. Reboot the machine and confirm without opening any terminal:
#    - Run in PowerShell after reboot: Get-Service -Name "ollama" → Running
#    - Check NSSM or Task Scheduler shows OrchestratorLoop and OrchestratorListener running
#    - Send !status from Discord on your phone
#    - Confirm bot responds with current project state
```

---

## Junction C — Headless local LLM verification

**When:** After Stage 12c is complete.

**What you are verifying:** The full system runs without any GUI open, survives a reboot, and is controllable entirely through Discord.

**Run this scenario:**

1. Reboot the Windows machine.
2. Do not open LM Studio, VS Code, or any terminal.
3. Wait 60 seconds for services to start.
4. Send `!status` from Discord on your phone.
5. Confirm the bot responds with current project state.
6. Send `!resume` if paused.
7. Confirm the orchestrator processes the next task and posts to Discord.

**Junction C pass criteria:**

- [ ] System recovers from reboot without manual intervention
- [ ] `!status` responds correctly from phone with no computer open
- [ ] Orchestrator uses Ollama — confirm by checking `agent-orchestrator/logs/orchestrator.stdout.log` shows `LOCAL_LLM_BASE_URL` pointing to port 11434
- [ ] No LM Studio or GUI dependency in the running system
- [ ] Log files are being written to `agent-orchestrator\logs\`
- [ ] `Get-Service -Name "ollama"` shows Status = Running after reboot
- [ ] NSSM or Task Scheduler shows both `OrchestratorLoop` and `OrchestratorListener` running after reboot

**Do not proceed to Stage 12d until all pass.**

---

## Stage 12d — Mode B hardening (Codex CLI automation)

### Objective

Enable `CODEX_MODE=auto` so the orchestrator invokes Codex CLI directly. Handle the case where Codex asks clarifying questions during a run. Add safeguards to prevent runaway automation.

### Pre-requisites before writing any code

Manually test Codex CLI non-interactive behaviour first:

```bash
# Test 1: does Codex run non-interactively from a prompt file?
codex run --prompt-file agent-orchestrator/last_prompt.md

# Test 2: what happens when the prompt is ambiguous?
# Create a deliberately vague last_prompt.md and observe whether Codex:
#   a) asks a question and waits for input
#   b) makes a decision and proceeds
#   c) exits with an error
```

Document what you observe — it determines how much hardening is needed in the Codex invocation logic.

### Codex prompt

```
Read docs/AGENT_ORCHESTRATOR_PLAN.md and docs/AGENT_ORCHESTRATOR_PRODUCTION_PLAN.md first.

I am implementing Stage 12d: Mode B hardening.

File to modify: agent-orchestrator/orchestrator.py
Files to inspect: agent-orchestrator/discord_notifier.py, agent-orchestrator/activity_logger.py
All other files are off-limits.

Update the CODEX_MODE=auto branch in the --run-loop implementation as follows:

1. Before invoking Codex, post to Discord:
   "[ORCHESTRATOR] Invoking Codex on Task {id}: {title}. Awaiting completion..."

2. Invoke Codex with a timeout:
   result = subprocess.run(
       ["codex", "run", "--prompt-file", "agent-orchestrator/last_prompt.md"],
       capture_output=True, text=True,
       timeout=int(os.getenv("CODEX_TIMEOUT_SECONDS", "300"))
   )

3. After Codex exits, check return code:
   - Return code 0: proceed to validator
   - Return code non-zero OR stdout contains question indicators
     (lines ending in "?", phrases like "which file", "did you mean", "please clarify"):
       a. Post Codex stdout/stderr to Discord truncated to 1500 chars:
          "[ORCHESTRATOR · CODEX QUESTION] Task {id} needs clarification:\n{output}\nReply !clarify <your answer> or !skip-task to skip this task"
       b. Set paused=1
       c. Break loop (human reads output, decides, resumes)

4. Add !clarify <text> command handling in discord_listener.py:
   - Appends the clarification text to last_prompt.md
   - Sets paused=0
   - Posts: "Clarification added. Orchestrator will retry on resume."

5. Add !skip-task command handling in discord_listener.py:
   - Marks current task as "skipped" in state.sqlite
   - Sets paused=0
   - Posts: "Task skipped. Orchestrator will move to next task on resume."

6. Add CODEX_TIMEOUT_SECONDS to .env.example (default 300)

7. Add a MAX_AUTO_TASKS_PER_SESSION env var (default 10):
   - Track tasks completed in current loop session
   - When limit reached: post to Discord "Session limit reached ({n} tasks). Send !resume to continue."
   - Set paused=1, break loop
   - This prevents unlimited autonomous runs without periodic human review

Do NOT modify any other file except discord_listener.py for the two new commands.
```

### Verification after Stage 12d

**Test 1 — Happy path:**
```bash
# Set a simple, unambiguous task as current in state.sqlite
# Run loop in auto mode
CODEX_MODE=auto python orchestrator.py --run-loop
# Expected: Codex invoked, completes, validator runs, success posted to Discord
```

**Test 2 — Codex question detection:**
```bash
# Replace last_prompt.md with a deliberately ambiguous prompt
# Manually trigger Codex invocation
# Expected: question detected, posted to Discord, loop pauses
# Send !clarify <answer> in Discord
# Expected: clarification appended, loop resumes on !resume
```

**Test 3 — Session limit:**
```bash
# Set MAX_AUTO_TASKS_PER_SESSION=2
# Run loop with enough tasks queued
# Expected: after 2 tasks, loop pauses and posts session limit message
```

**Test 4 — Timeout:**
```bash
# Set CODEX_TIMEOUT_SECONDS=5 temporarily
# Run loop — Codex will timeout
# Expected: timeout caught, posted to Discord, loop pauses
```

---

## Junction D — Full Mode B end-to-end verification

**When:** After Stage 12d is complete.

**What you are verifying:** The fully autonomous loop works correctly through a complete task cycle with no manual intervention except Discord commands.

**Run this scenario with close monitoring:**

```bash
# Terminal 1 (or as system service)
python discord_listener.py

# Terminal 2 (or as system service)
CODEX_MODE=auto python orchestrator.py --run-loop
```

**Scenario:**

1. Queue one simple, low-risk task as current.
2. Start both processes.
3. Watch Discord for: start notification → Codex invocation notification → result.
4. Confirm Codex output was applied to the repo (check `git diff`).
5. Confirm validator passed.
6. Confirm `ACTIVITY.md` has complete entry.
7. Send `!pause` — confirm loop stops before starting next task.
8. Send `!resume` — confirm loop continues.
9. Let loop hit the phase gate — confirm approval request posted to Discord.
10. Send `!approve phase-{N}-exit` — confirm loop advances to next phase.

**Junction D pass criteria:**

- [ ] Full task cycle completes without manual terminal intervention
- [ ] Codex output is correctly applied (git diff shows expected changes)
- [ ] Validator catches deliberate bad change before it's logged as done
- [ ] `!pause` stops loop cleanly (no half-completed task)
- [ ] `!resume` restarts from correct position (not re-running completed task)
- [ ] Phase gate blocks correctly and unblocks on `!approve`
- [ ] Session limit triggers as configured
- [ ] All Discord messages are correctly formatted and arrive in order
- [ ] No exceptions in orchestrator or listener logs

**Only after Junction D passes is the system ready for unsupervised production operation.**

---

## Production run checklist

Before leaving the system to run unsupervised:

- [ ] Both processes running as system services (launchctl or systemd)
- [ ] Ollama running as system service, models pre-loaded
- [ ] `CODEX_MODE=auto` set in `.env`
- [ ] `MAX_AUTO_TASKS_PER_SESSION` set to a comfortable limit (recommend 5 for first week)
- [ ] `CODEX_TIMEOUT_SECONDS` set (recommend 300)
- [ ] `ORCHESTRATOR_APPROVAL_TIMEOUT_SECONDS` set (recommend 7200 — 2 hours for phase gates)
- [ ] Discord bot has MESSAGE CONTENT intent enabled
- [ ] Log rotation configured for `agent-orchestrator/logs/`
- [ ] You have tested `!pause` and `!resume` from your phone
- [ ] You know how to SSH in if Discord control fails
- [ ] `ACTIVITY.md` is being written to and readable
- [ ] A known-good task is queued as the first thing the system will do

---

## Summary: new files introduced in this plan

```
agent-orchestrator/
├── discord_listener.py          # Stage 12a — inbound Discord bot
├── logs/
│   ├── orchestrator.stdout.log  # Stage 12c — system service logs
│   └── orchestrator.stderr.log
└── .env additions:
    DISCORD_BOT_TOKEN=
    DISCORD_COMMAND_CHANNEL_ID=
    LOOP_INTERVAL_SECONDS=30
    CODEX_TIMEOUT_SECONDS=300
    MAX_AUTO_TASKS_PER_SESSION=10
```

New commands added to `discord_listener.py`:

| Command | Stage | Action |
|---|---|---|
| `!status` | 12a | Returns current phase and task from state.sqlite |
| `!approve <ref>` | 12a | Records approval in state.sqlite |
| `!reject <ref> <notes>` | 12a | Records rejection in state.sqlite |
| `!pause` | 12a | Sets paused=1 in settings table |
| `!resume` | 12a | Sets paused=0 in settings table |
| `!clarify <text>` | 12d | Appends clarification to last_prompt.md |
| `!skip-task` | 12d | Marks current task skipped, sets paused=0 |
