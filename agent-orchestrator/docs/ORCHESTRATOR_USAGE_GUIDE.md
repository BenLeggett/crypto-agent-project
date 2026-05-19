# Agent Orchestrator Usage Guide and Reference

Last updated: 2026-05-17

This guide explains how to run, test, and operate the `agent-orchestrator/`
tool after Stage 12D. It is written in two passes:

- a nontechnical operator guide for someone seeing the tool for the first time,
- a technical reference for setup, environment variables, commands, testing,
  and expected failure behavior.

The orchestrator is a development automation tool. It does not trade, deploy,
touch live wallet credentials, or bypass the project risk governor. Its job is
to pick the next documented development task, prepare a scoped Codex prompt,
optionally run Codex in auto mode, validate the repo deterministically, and
pause for a human whenever uncertainty or risk appears.

---

## Quick Safety Summary

- Default mode is manual: `CODEX_MODE=manual`.
- Auto mode must be enabled explicitly: `CODEX_MODE=auto`.
- Auto mode runs Codex only after orchestrator gates pass.
- Auto mode sends Codex the prompt through stdin with `codex exec`.
- Codex output is never enough to mark a task done. The deterministic validator
  must pass first.
- The loop pauses on prompt ambiguity, Codex timeout, Codex non-zero exit,
  Codex clarification output, validation failure, phase gate, risky task gate,
  or session limit.
- Secrets stay manual. Do not commit `.env`, Discord tokens, API keys, exchange
  keys, wallet data, webhook URLs, or live config credentials.

---

# Part 1: Nontechnical Operator Guide

## What This Tool Does

Think of the orchestrator as a project coordinator for development work:

1. It reads the project task list.
2. It finds the next eligible task.
3. It writes instructions for Codex into `agent-orchestrator/last_prompt.md`.
4. In manual mode, it waits for a person to apply those instructions.
5. In auto mode, it can run Codex itself.
6. It validates the result.
7. It reports progress through Discord or local mock output.
8. It stops and asks for help when something is risky, unclear, or broken.

It is intentionally cautious. Pausing is normal and healthy.

## The Two Modes

### Manual Mode

Manual mode is safest and is the default.

What happens:

1. The orchestrator prepares `last_prompt.md`.
2. It pauses.
3. A person reviews and applies the prompt.
4. The person sends `!resume`.
5. The orchestrator validates the work.

Use manual mode when:

- you are testing the system,
- you want to review every Codex prompt before changes happen,
- the task is broad, sensitive, or new.

### Auto Mode

Auto mode lets the orchestrator invoke Codex directly.

What happens:

1. The orchestrator prepares `last_prompt.md`.
2. It checks the prompt has a strict task contract.
3. It blocks if the prompt is vague or incomplete.
4. It runs Codex with `codex exec`.
5. It reads Codex's final response file.
6. It validates the repository.
7. It marks the task done only if validation passes.
8. It stops after the configured session limit.

Use auto mode only after manual mode is working and Codex CLI has been tested.

## Discord Commands

Use these from the approved Discord command channel:

```text
!status
!pause
!resume
!approve <ref>
!reject <ref> <notes>
!explain
!clarify <task_id> <details>
!skip-task <task_id>
```

What the important commands mean:

- `!status`: show what the orchestrator is doing.
- `!pause`: stop the loop before it starts more work.
- `!resume`: continue after a pause.
- `!approve <ref>`: approve a phase gate or risky task gate.
- `!reject <ref> <notes>`: reject a gate with a reason.
- `!explain`: ask for a read-only explanation of the latest state.
- `!clarify <task_id> <details>`: add human guidance when Codex or the prompt
  needs clarification.
- `!skip-task <task_id>`: skip the current or awaiting task and keep the loop
  paused until review.

## Discord Dashboard Card

In Discord mode, the listener maintains one bot-owned task run card. The card is
the operator dashboard for the current project state. It tells the story in six
fields:

- `Status`: the current headline state, such as Prompt ready, Codex running,
  Needs clarification, Codex timed out, Failed validation, or Complete.
- `Progress`: a compact timeline of recent events.
- `Current Step`: what just happened or what is happening now.
- `Finding`: the latest failure, diagnosis, Codex issue, or session-limit note.
- `Models`: local low/medium model readiness for advisory explanations.
- `Next Action`: the safest next operator move.

Buttons appear only when they are currently safe and useful:

- `Status` and `Explain` are generally available while work is idle.
- `Pause` appears when the loop is running.
- `Resume` appears when the loop is paused and retrying is appropriate.
- `Approve` and `Reject` appear only for pending approval refs.
- `Deep Diagnose` appears only for failed tasks.
- `Clarify Task <id>` appears only when the orchestrator is waiting for human
  clarification. In Discord mode this opens a text modal.
- `Skip Task <id>` appears when a current or awaiting task can be skipped.

Buttons are hidden while validation, Codex execution, or medium diagnosis is in
flight. This prevents competing actions from being selected while the project
state is changing.

## What Normal Operation Looks Like

Manual mode:

```text
Start loop
Prompt ready
Paused
Human reviews last_prompt.md
Human applies changes
Human sends !resume
Validation runs
Task passes or fails
```

Auto mode:

```text
Start loop
Prompt generated
Prompt contract linted
Codex invoked
Codex response captured
Validation runs
Task marked done only if validation passes
Loop continues until pause, gate, failure, or session limit
```

## When the Tool Stops

The orchestrator stops on purpose when it needs a human.

Common messages:

- `PROMPT BLOCKED`: the task prompt is missing required contract details or is
  too vague.
- `CODEX TIMEOUT`: Codex exceeded `CODEX_TIMEOUT_SECONDS`.
- `CODEX QUESTION`: Codex asked for clarification or produced ambiguous output.
- `CODEX FAILURE`: Codex exited with an error.
- `Validation failed`: the deterministic validator rejected the repo state.
- `Session limit reached`: auto mode completed enough tasks for this session.

What to do:

- Read the Discord message.
- Run `!status`.
- Use `!explain` if you want more context.
- Use `!clarify <task_id> <details>` if the task needs more instruction.
- Use `!skip-task <task_id>` if the task should not be attempted now.
- Use `!resume` only after you are ready for the loop to continue.

---

# Part 2: Technical Reference

## Repository Layout

Important files:

```text
agent-orchestrator/orchestrator.py
agent-orchestrator/discord_listener.py
agent-orchestrator/prompt_runner.py
agent-orchestrator/validator.py
agent-orchestrator/last_prompt.md
agent-orchestrator/codex_last_message.md
agent-orchestrator/state.sqlite
agent-orchestrator/.env.example
agent-orchestrator/docs/AGENT_ORCHESTRATOR_PLAN.md
agent-orchestrator/docs/AGENT_ORCHESTRATOR_PRODUCTION_PLAN.md
agent-orchestrator/docs/adjusted_prestage_12d_and_stage_12d_exec_stdin.md
```

Runtime state:

- `state.sqlite`: task status, pause flag, approvals, operator events.
- `last_prompt.md`: the prompt prepared for the current task.
- `codex_last_message.md`: final assistant message from `codex exec`.
- `ACTIVITY.MD`: audit timeline.

## Environment Setup

Use `agent-orchestrator/.env.example` as the reference. Keep real secrets in an
untracked local `.env`.

Minimum local/manual setup:

```dotenv
PROJECT_ROOT=..
CODEX_MODE=manual
LOOP_INTERVAL_SECONDS=30
LOCAL_VALIDATION_SUMMARY=failures_only
```

Local LLM advisory setup, usually Ollama:

```dotenv
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_API_KEY=ollama
LOCAL_LLM_LOW_MODEL=qwen2.5:3b
LOCAL_LLM_MEDIUM_MODEL=gemma4:latest
LOCAL_LLM_LOW_TIMEOUT_SECONDS=30
LOCAL_LLM_LOW_MAX_TOKENS=256
LOCAL_LLM_MEDIUM_WARMUP_TIMEOUT_SECONDS=120
LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS=180
```

Discord setup:

```dotenv
DISCORD_WEBHOOK_URL=
DISCORD_BOT_TOKEN=
DISCORD_COMMAND_CHANNEL_ID=
DISCORD_WEBHOOK_RETRY_ATTEMPTS=3
DISCORD_WEBHOOK_RETRY_BACKOFF_SECONDS=1
```

Codex auto-mode setup:

```dotenv
CODEX_MODE=manual
CODEX_MODEL=
CODEX_TIMEOUT_SECONDS=300
MAX_AUTO_TASKS_PER_SESSION=5
CODEX_ENABLE_SEARCH=false
CODEX_LAST_MESSAGE_PATH=agent-orchestrator/codex_last_message.md
```

Notes:

- Leave `CODEX_MODE=manual` until you have completed manual verification.
- Set `CODEX_MODEL` only if the installed Codex CLI accepts that model id.
- Set `CODEX_ENABLE_SEARCH=true` only for tasks that genuinely need current web
  information.
- `CLOUD_HIGH_MODEL` affects the orchestrator's own cloud review calls. It does
  not select the Codex CLI implementation model.
- `CODEX_MODEL` affects the Codex CLI subprocess only. It does not affect
  orchestrator local/cloud model calls.

## First-Time Local Verification

Run from repo root:

```powershell
python -m pytest agent-orchestrator
python -m py_compile agent-orchestrator/orchestrator.py agent-orchestrator/discord_listener.py agent-orchestrator/prompt_runner.py
python agent-orchestrator/orchestrator.py --status
python agent-orchestrator/orchestrator.py --run-next
```

Expected:

- tests pass,
- status prints the current phase and active task,
- `--run-next` writes `agent-orchestrator/last_prompt.md`,
- `last_prompt.md` starts with `# Codex Task Contract`.

Optional contract check:

```powershell
python -c "import sys; sys.path.insert(0, 'agent-orchestrator'); import orchestrator; text=open('agent-orchestrator/last_prompt.md', encoding='utf-8').read(); print(orchestrator.lint_codex_prompt_contract(text))"
```

Expected:

```text
[]
```

## Running in Mock Mode

Mock mode does not require Discord credentials.

Terminal 1:

```powershell
python agent-orchestrator/discord_listener.py
```

Type commands into the listener:

```text
!status
!pause
!resume
!explain
```

Terminal 2, manual loop:

```powershell
$env:CODEX_MODE="manual"
python agent-orchestrator/orchestrator.py --run-loop
```

Expected:

- loop starts,
- prompt is prepared,
- loop sets `paused=1`,
- listener can show status,
- `!resume` clears the pause flag.

## Running With Discord

Prerequisites:

- Discord bot token wired in local `.env`,
- command channel id wired,
- bot invited to the server,
- message content intent enabled,
- webhook URL wired if outbound webhook messages are desired.

Terminal 1:

```powershell
python agent-orchestrator/discord_listener.py
```

Terminal 2:

```powershell
$env:CODEX_MODE="manual"
python agent-orchestrator/orchestrator.py --run-loop
```

From Discord:

```text
!status
!pause
!resume
```

Expected:

- Discord shows one evolving task run card,
- buttons disappear while work is in flight,
- routine run-loop events are stored in SQLite instead of spamming the channel,
- validation failures remain paused until human action.

## Testing Codex CLI Stdin Shape

Only run this after Codex CLI is installed and authenticated.

```powershell
Set-Content agent-orchestrator\last_prompt.md "Create agent-orchestrator/codex_headless_test.txt containing the text 'headless test ok'. Do not modify anything else."
$prompt = Get-Content agent-orchestrator\last_prompt.md -Raw

$prompt | codex exec -C . -s workspace-write -c approval_policy='"never"' -o agent-orchestrator\codex_last_message.md -
```

Expected:

- `agent-orchestrator/codex_headless_test.txt` exists,
- `agent-orchestrator/codex_last_message.md` exists,
- no unrelated files are modified.

Cleanup:

```powershell
Remove-Item agent-orchestrator\codex_headless_test.txt
git status --short
```

## Running Auto Mode

Auto mode should be used only after:

- `python -m pytest agent-orchestrator` passes,
- `--run-next` writes a valid task contract,
- Codex CLI stdin smoke test passes,
- Discord pause/resume/status are verified,
- `MAX_AUTO_TASKS_PER_SESSION` is set to a comfortable review limit.

Start with a low session limit:

```powershell
$env:CODEX_MODE="auto"
$env:MAX_AUTO_TASKS_PER_SESSION="1"
$env:CODEX_TIMEOUT_SECONDS="300"
python agent-orchestrator/orchestrator.py --run-loop
```

Expected:

1. The loop selects the next task.
2. Risk and phase gates still apply.
3. `last_prompt.md` is generated.
4. The prompt contract is linted.
5. Codex runs through stdin.
6. Codex's final message is written to `codex_last_message.md`.
7. The deterministic validator runs.
8. The task is marked `done` only if validation passes.
9. The loop pauses after the session limit.

## Stage 12D Auto-Mode Behavior

Codex command shape:

```python
[
    "codex",
    "exec",
    "-C",
    project_root,
    "-s",
    "workspace-write",
    "-c",
    'approval_policy="never"',
    "-o",
    codex_last_message_path,
    "-",
]
```

Optional additions:

- `--search` is added only when `CODEX_ENABLE_SEARCH=true`.
- `-m <model>` is added only when `CODEX_MODEL` is not empty.

Before invocation:

- prior `codex_last_message.md` is removed if present,
- `last_prompt.md` must contain all required contract fields,
- vague phrases such as `fix the issue` and `do the right thing` block launch.

After invocation:

- stdout, stderr, and `codex_last_message.md` are inspected together,
- `CODEX_NEEDS_CLARIFICATION:` pauses the loop,
- likely clarification phrases pause the loop,
- non-zero exit pauses the loop,
- timeout pauses the loop,
- return code 0 proceeds to deterministic validation.

## Prompt Contract Fields

Every auto-mode prompt must include:

```text
TASK_ID:
TASK_TITLE:
OBJECTIVE:
FILES_ALLOWED_TO_MODIFY:
FILES_ALLOWED_TO_INSPECT:
OUT_OF_SCOPE:
ACCEPTANCE_CRITERIA:
VALIDATION_COMMANDS:
STOP_CONDITIONS:
```

Blocked vague phrases:

```text
fix the issue
do the right thing
make it better
clean this up
improve the project
handle it
whatever is needed
```

## Failure and Recovery Reference

### Prompt Blocked

Meaning:

- `last_prompt.md` is missing required fields or contains vague language.

Recovery:

```text
!clarify <task_id> <specific scope/details>
!resume
```

Or update the task docs and rerun prompt generation.

### Codex Timeout

Meaning:

- Codex exceeded `CODEX_TIMEOUT_SECONDS`.

Recovery:

```text
!resume
```

Or:

```text
!skip-task <task_id>
```

### Codex Question

Meaning:

- Codex printed `CODEX_NEEDS_CLARIFICATION:` or likely clarification text.

Recovery:

```text
!clarify <task_id> <answer>
!resume
```

In Discord mode, use the `Clarify Task <id>` button to open a text box, then
send `!resume` after the clarification is added.

### Codex Failure

Meaning:

- Codex exited with a non-zero return code.

Recovery:

- inspect Discord output and `codex_last_message.md`,
- repair environment or prompt,
- use `!resume` to retry or `!skip-task <task_id>` to skip.

### Validation Failure

Meaning:

- Codex returned successfully, but deterministic validation failed.

Recovery:

- inspect `!status`,
- use `!explain`,
- repair manually,
- use `!resume` to re-run validation.

### Session Limit

Meaning:

- Auto mode completed `MAX_AUTO_TASKS_PER_SESSION` successful cycles.

Recovery:

```text
!status
!resume
```

Only resume after reviewing the completed changes.

## Validation Commands

Fast orchestrator-only validation:

```powershell
python -m pytest agent-orchestrator
```

Compile key modules:

```powershell
python -m py_compile agent-orchestrator/orchestrator.py agent-orchestrator/discord_listener.py agent-orchestrator/prompt_runner.py
```

Project validation through orchestrator:

```powershell
python agent-orchestrator/orchestrator.py --validate
```

Broader project validation when needed:

```powershell
python -m pytest
make test
```

Some Make targets may be optional on Windows. The validator treats missing
optional Make targets as warnings when configured by the existing validator
logic.

## Operating Expectations

Healthy signs:

- `CODEX_MODE=manual` remains the default until intentionally changed,
- `last_prompt.md` begins with `# Codex Task Contract`,
- `state.sqlite` records task status and operator events,
- `ACTIVITY.MD` receives milestone and task entries,
- Discord controls return after in-flight work ends,
- failed tasks remain failed until validation passes.

Unhealthy signs:

- `.env` appears in `git status`,
- `codex_last_message.md` is missing after auto runs,
- the loop repeatedly pauses on the same task without new clarification,
- validation is skipped,
- tasks are marked done after timeout, prompt block, or Codex failure.

## Production Checklist

Before leaving the orchestrator unattended:

- Follow `agent-orchestrator/docs/MODE_B_UNATTENDED_READINESS_CHECKLIST.md`
  end to end.
- `python -m pytest agent-orchestrator` passes.
- Codex CLI stdin smoke test passes.
- `CODEX_MODE=auto` is intentionally set.
- `MAX_AUTO_TASKS_PER_SESSION` is conservative, such as `1` to `5`.
- `CODEX_TIMEOUT_SECONDS` is set.
- Discord `!status`, `!pause`, `!resume`, `!clarify`, and `!skip-task` are tested.
- Phase approval gates still require `!approve`.
- `ACTIVITY.MD` is updating.
- `.env` is not tracked.
- No live trading or wallet execution is enabled by this tool.

## What Remains Manual

These items require human-owned secrets or decisions:

- Discord webhook URL,
- Discord bot token,
- Discord command channel id,
- OpenAI or other provider API keys,
- Ollama model installation,
- Codex CLI installation and login,
- service setup through Task Scheduler or NSSM,
- any exchange or wallet credential wiring,
- any live-mode promotion decision.

Manual wiring details belong in `docs/MANUAL_WIRING_CHECKLIST.md`. Live trading
remains gated by the main project promotion process and is not enabled by the
orchestrator.
