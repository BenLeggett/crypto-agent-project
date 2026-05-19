# Adjusted Pre-Stage 12d and Stage 12d — Codex `exec` Headless Automation

## Summary

This document replaces the earlier `codex run --prompt-file` design with the confirmed `codex exec` interface from the installed Codex CLI.

The main correction is that Mode B automation should invoke Codex non-interactively using:

```powershell
$prompt = Get-Content agent-orchestrator\last_prompt.md -Raw

$prompt | codex exec - `
  -C . `
  -s workspace-write `
  -c approval_policy='"never"' `
  -o agent-orchestrator\codex_last_message.md
```

In Python subprocess form, this means:

```python
codex_cmd = [
    "codex",
    "exec",
    "-",  # Read prompt from stdin.
    "-C",
    project_root,
    "-s",
    "workspace-write",
    "-c",
    'approval_policy="never"',
    "-o",
    str(codex_last_message_path),
]

result = subprocess.run(
    codex_cmd,
    input=prompt_text,
    capture_output=True,
    text=True,
    timeout=timeout_seconds,
    cwd=project_root,
)
```

This is now the preferred Stage 12d invocation strategy because:

- `codex exec` is the confirmed non-interactive command.
- `-` tells Codex to read the prompt from stdin.
- stdin avoids Windows command-line length problems.
- `-s workspace-write` is directly supported by `codex exec`.
- `-c approval_policy="never"` replaces the unsupported `--ask-for-approval never` flag.
- `-o agent-orchestrator/codex_last_message.md` gives the orchestrator a stable final-output file to inspect.
- The orchestrator, not Codex, owns the human approval gates.

## Flow Overview

### Pre-Stage 12d Flow

```text
Inspect installed Codex CLI
        ↓
Confirm `codex exec` options
        ↓
Run a tiny stdin-based headless test
        ↓
Run a deliberately vague prompt test
        ↓
Confirm Codex may proceed anyway
        ↓
Add prompt contract + prompt lint gate requirement
        ↓
Update .env.example for Mode B automation
```

### Stage 12d Runtime Flow

```text
orchestrator --run-loop
        ↓
find next eligible task
        ↓
check orchestrator approval gates
        ↓
generate last_prompt.md
        ↓
lint last_prompt.md for strict task contract
        ↓
if prompt incomplete:
    block Codex invocation
    post Discord message
    pause loop
        ↓
if prompt valid:
    invoke `codex exec -` with prompt through stdin
        ↓
write final Codex message to codex_last_message.md
        ↓
inspect return code + stdout/stderr + codex_last_message.md
        ↓
if timeout / failure / clarification marker:
    post Discord message
    pause loop
        ↓
if Codex success:
    run validator
        ↓
if validation passes:
    mark task done
    log ACTIVITY.md
    continue until session limit / phase gate / pause
```

---

# Pre-Stage 12d — Codex CLI Capability Check for Headless Mode

## Completion Note

As of 2026-05-17, the stdin-based `codex exec` capability check has been
confirmed externally on the target machine. The repository now includes the
pre-stage scaffolding needed before the full Stage 12d loop implementation:

- generated `last_prompt.md` content begins with a strict Codex task contract,
- `orchestrator.py` exposes reusable prompt-contract linting for Stage 12d,
- `prompt_runner.assemble_prompt()` writes the rendered prompt to disk,
- `agent-orchestrator/.env.example` contains Mode B automation placeholders,
- the production plan points Stage 12d implementers to this adjusted stdin
  design instead of the older `codex run --prompt-file` command shape.

## Objective

Confirm the exact installed Codex CLI behavior before implementing Stage 12d automation.

The orchestrator and Codex CLI use separate routing/configuration systems:

| System | Controlled by | Purpose |
|---|---|---|
| Orchestrator local reasoning | `LOCAL_LLM_*` | Status summaries, simple local reasoning, prompt/context support |
| Orchestrator cloud reasoning | `OPENAI_API_KEY`, `CLOUD_HIGH_MODEL`, `CLOUD_EXTRA_HIGH_MODEL` | Phase review, risk review, failed-task diagnosis |
| Codex CLI implementation | `codex exec`, `CODEX_MODEL`, Codex CLI config/flags | Actual code modification subprocess |

Changing `CLOUD_HIGH_MODEL` does not change the Codex implementation model. Changing `CODEX_MODEL` does not change the orchestrator's own reasoning calls.

## Step 1 — Inspect the installed CLI

Run:

```powershell
codex --help
codex exec --help
codex features list
```

The important confirmed `codex exec` capabilities are:

```text
Usage: codex exec [OPTIONS] [PROMPT]
       codex exec [OPTIONS] <COMMAND> [ARGS]
```

Prompt input behavior:

```text
If PROMPT is not provided as an argument, or if `-` is used, instructions are read from stdin.
If stdin is piped and a prompt is also provided, stdin is appended as a `<stdin>` block.
```

Relevant options:

| Option | Meaning | Stage 12d usage |
|---|---|---|
| `-C, --cd <DIR>` | Set Codex working root | Required |
| `-s, --sandbox <MODE>` | Select sandbox policy | Use `workspace-write` |
| `-c, --config <key=value>` | Override Codex config | Use `approval_policy="never"` |
| `-m, --model <MODEL>` | Select Codex model | Optional, if `CODEX_MODEL` is set |
| `--oss` | Use open-source provider | Not required for Stage 12d |
| `--local-provider <lmstudio|ollama>` | Select local provider | Optional later, not required now |
| `--enable <FEATURE>` | Enable feature flag | Do not depend on unstable features for Stage 12d |
| `--disable <FEATURE>` | Disable feature flag | Optional for hardening if needed |
| `--json` | Emit JSONL events | Defer to a later structured logging stage |
| `-o, --output-last-message <FILE>` | Write final Codex message to file | Required/recommended |
| `--output-schema <FILE>` | Force final response shape | Useful later; not required for Stage 12d |
| `--ephemeral` | Do not persist session files | Optional; do not enable by default |
| `--ignore-user-config` | Ignore user config | Optional hardening; only use if config drift becomes a problem |
| `--ignore-rules` | Ignore execpolicy rules | Do not use by default |
| `--dangerously-bypass-approvals-and-sandbox` | Disable safety controls | Never use for this workflow |

## Step 2 — Interpret available features

From `codex features list`, treat feature status as follows.

### Safe to acknowledge, but not required for Stage 12d

These may be useful later but should not be central to Stage 12d:

```text
browser_use                 stable true
computer_use                stable true
fast_mode                   stable true
guardian_approval           stable true
multi_agent                 stable true
shell_snapshot              stable true
shell_tool                  stable true
tool_call_mcp_elicitation   stable true
tool_search                 stable true
workspace_dependencies      stable true
```

### Do not build Stage 12d around these

These are disabled, under development, experimental, removed, or otherwise not appropriate as required dependencies for the headless loop:

```text
multi_agent_v2              under development false
enable_fanout               under development false
remote_control              under development false
exec_permission_approvals   under development false
unified_exec                stable false
memories                    experimental false
prevent_idle_sleep          experimental false
```

### Practical interpretation

Stage 12d should remain intentionally boring:

```text
subprocess invocation
prompt linting
timeout handling
Codex final message capture
validation
Discord pause/resume/clarify/skip controls
session limit
activity logging
```

Do not require multi-agent, remote control, browser control, JSON event parsing, or output schemas in Stage 12d.

## Step 3 — Confirm the working command shape manually

Create a small test prompt:

```powershell
Set-Content agent-orchestrator\last_prompt.md "Create agent-orchestrator/codex_headless_test.txt containing the text 'headless test ok'. Do not modify anything else."
```

Run Codex through stdin:

```powershell
$prompt = Get-Content agent-orchestrator\last_prompt.md -Raw

$prompt | codex exec - `
  -C . `
  -s workspace-write `
  -c approval_policy='"never"' `
  -o agent-orchestrator\codex_last_message.md
```

Expected:

```text
agent-orchestrator/codex_headless_test.txt exists
agent-orchestrator/codex_last_message.md exists
No unrelated files modified
```

Clean up:

```powershell
Remove-Item agent-orchestrator\codex_headless_test.txt
```

Check status:

```powershell
git status --short
```

## Step 4 — Confirm vague prompts are unsafe

Test:

```powershell
Set-Content agent-orchestrator\last_prompt.md "Fix the issue in the project. Do the right thing."
$prompt = Get-Content agent-orchestrator\last_prompt.md -Raw

$prompt | codex exec - `
  -C . `
  -s workspace-write `
  -c approval_policy='"never"' `
  -o agent-orchestrator\codex_last_message.md
```

Observation:

```text
Codex may proceed anyway instead of asking a clarification question.
```

Conclusion:

```text
Stage 12d must not rely on Codex asking questions after launch.
The orchestrator must block underspecified prompts before invoking Codex.
```

## Step 5 — Add Mode B environment variables

Add these to `agent-orchestrator/.env.example` and local `.env`:

```dotenv
# =========================
# Codex CLI automation
# =========================

# manual = generate prompt only
# auto = orchestrator invokes Codex CLI directly after required gates pass
CODEX_MODE=manual

# Optional. Passed to `codex exec -m` if set.
# Must match a model identifier accepted by your installed Codex CLI.
CODEX_MODEL=

# Maximum seconds for one Codex subprocess before the loop pauses.
CODEX_TIMEOUT_SECONDS=300

# Maximum successfully completed Codex+validation task cycles before pausing.
MAX_AUTO_TASKS_PER_SESSION=5

# Optional. Enables Codex web/search capability only when explicitly needed.
CODEX_ENABLE_SEARCH=false

# File where Codex writes the final assistant message for orchestrator inspection.
CODEX_LAST_MESSAGE_PATH=agent-orchestrator/codex_last_message.md
```

Remove or avoid relying on:

```dotenv
CODEX_MAX_POSITIONAL_PROMPT_CHARS=24000
CODEX_THINKING_LEVEL=
```

Reason:

- Positional prompt length limits are no longer relevant if prompts are passed through stdin.
- The provided `codex exec --help` output does not confirm a thinking/reasoning-depth flag.

## Step 6 — Add prompt contract requirement

Every `last_prompt.md` intended for auto mode must include a strict task contract.

Required fields:

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

If any required field is missing, the orchestrator must block before invoking Codex.

---

# Stage 12d — Mode B Hardening with `codex exec` + stdin

## Objective

Enable `CODEX_MODE=auto` so the orchestrator can run a remote/headless development loop:

```text
select task
build scoped prompt
lint prompt
invoke Codex CLI
validate changes
log activity
notify Discord
continue until pause, failure, approval gate, phase gate, or session limit
```

Human involvement should be required only for:

```text
approval-required gates
prompt clarification
validation failures
timeouts
manual pause/resume
skip-task decisions
phase transitions
session-limit review
```

## Completion Note

As of 2026-05-17, Stage 12d main implementation is complete in the local
orchestrator code:

- auto mode lints `last_prompt.md` before Codex invocation,
- Codex runs through `codex exec` with prompt text passed on stdin,
- optional `CODEX_MODEL` and `CODEX_ENABLE_SEARCH` are included only when set,
- `CODEX_LAST_MESSAGE_PATH` is cleared before each run and inspected afterward,
- timeout, clarification, and non-zero exit paths pause without marking done,
- deterministic validation remains the only success gate after Codex returns 0,
- successful auto cycles count toward `MAX_AUTO_TASKS_PER_SESSION`,
- Discord `!clarify <task_id> <details>` and `!skip-task <task_id>` are wired.

## Files allowed to modify

```text
agent-orchestrator/orchestrator.py
agent-orchestrator/discord_listener.py
agent-orchestrator/.env.example
```

## Files allowed to inspect

```text
agent-orchestrator/discord_notifier.py
agent-orchestrator/activity_logger.py
agent-orchestrator/validator.py
agent-orchestrator/decision_gate.py
agent-orchestrator/prompt_runner.py
agent-orchestrator/task_queue_reader.py
agent-orchestrator/context_builder.py
```

Do not modify project files outside `agent-orchestrator/` for this stage.

---

## Required Stage 12d Implementation

### 1. Add strict Codex prompt contract to auto mode

Before invoking Codex, read:

```text
agent-orchestrator/last_prompt.md
```

Validate that it contains:

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

Also block vague phrases:

```text
fix the issue
do the right thing
make it better
clean this up
improve the project
handle it
whatever is needed
```

If blocked:

```text
[ORCHESTRATOR · PROMPT BLOCKED]
Codex was not invoked because the prompt is underspecified.

Issues:
- <issue 1>
- <issue 2>

Reply !clarify <task_id> <details> or update the task docs.
```

Set `paused=1` and break the loop.

### 2. Add a canonical task contract to generated prompts

The assembled `last_prompt.md` for auto mode should begin with:

```markdown
# Codex Task Contract

You are running in a headless automation loop.

You must not infer missing scope.

If the task objective, allowed modification files, acceptance criteria, or validation commands are unclear, stop without modifying files and print:

CODEX_NEEDS_CLARIFICATION:
<specific missing information>

Do not make a best-effort implementation when the task contract is incomplete.

TASK_ID: <task id>
TASK_TITLE: <task title>

OBJECTIVE:
<one concrete implementation objective>

FILES_ALLOWED_TO_MODIFY:
- <specific path>

FILES_ALLOWED_TO_INSPECT:
- <specific path>

OUT_OF_SCOPE:
- Do not modify files outside FILES_ALLOWED_TO_MODIFY.
- Do not refactor unrelated code.
- Do not introduce new dependencies unless explicitly listed.
- Do not change environment files, secrets, CI, deployment, or live config.
- Do not make architectural changes unless explicitly requested.

ACCEPTANCE_CRITERIA:
- <specific expected result>

VALIDATION_COMMANDS:
- <command to run, or "none specified">

STOP_CONDITIONS:
- If the target file is unclear, stop and explain the ambiguity.
- If required context is missing, stop and explain what is missing.
- If implementation requires modifying files outside FILES_ALLOWED_TO_MODIFY, stop.
- If tests or validation commands are missing and correctness cannot be verified, stop.
- If secrets, credentials, live config, deployment, or risky paths are required, stop.
```

### 3. Use `codex exec -` and stdin

Do not pass the prompt as a positional command-line argument.

Use:

```python
codex_cmd = [
    "codex",
    "exec",
    "-",  # Read prompt from stdin.
    "-C",
    project_root,
    "-s",
    "workspace-write",
    "-c",
    'approval_policy="never"',
    "-o",
    str(codex_last_message_path),
]
```

Run:

```python
result = subprocess.run(
    codex_cmd,
    input=prompt_text,
    capture_output=True,
    text=True,
    timeout=int(os.getenv("CODEX_TIMEOUT_SECONDS", "300")),
    cwd=project_root,
)
```

### 4. Add optional model selection

If `CODEX_MODEL` is set:

```python
codex_cmd += ["-m", os.getenv("CODEX_MODEL")]
```

Do not add model flags if `CODEX_MODEL` is empty.

### 5. Add optional search only when configured

If `CODEX_ENABLE_SEARCH=true`, add:

```python
codex_cmd += ["--search"]
```

Only use this for tasks that genuinely need current information. Default remains false.

### 6. Capture final Codex response file

Use:

```text
CODEX_LAST_MESSAGE_PATH=agent-orchestrator/codex_last_message.md
```

Before each Codex run, delete or overwrite the previous file.

After Codex exits, read:

```python
last_message = codex_last_message_path.read_text(encoding="utf-8")
```

If the file does not exist, continue using captured stdout/stderr, but add a warning.

### 7. Timeout behavior

On `subprocess.TimeoutExpired`:

- Post Discord timeout message.
- Set `paused=1`.
- Store current task as blocked/awaiting review.
- Do not mark task done.
- Log activity.
- Break the loop.

Message:

```text
[ORCHESTRATOR · CODEX TIMEOUT]
Task {id}: {title}
Codex exceeded CODEX_TIMEOUT_SECONDS={n}.
Loop paused. Reply !resume to retry or !skip-task {id} to skip.
```

### 8. Clarification detection after Codex exits

Inspect combined:

```text
stdout
stderr
codex_last_message.md
```

Primary detection marker:

```text
CODEX_NEEDS_CLARIFICATION:
```

Secondary phrases:

```text
please clarify
could you clarify
which file
which directory
did you mean
do you want me to
should I
I need more information
ambiguous
```

If detected:

- Post truncated output to Discord.
- Set `paused=1`.
- Store the current task id as awaiting clarification.
- Do not mark task done.
- Break the loop.

Message:

```text
[ORCHESTRATOR · CODEX QUESTION]
Task {id}: {title} needs clarification.

{truncated_output}

Reply !clarify {id} <your answer> or !skip-task {id}
```

### 9. Non-zero exit behavior

If `result.returncode != 0`:

- Post failure summary to Discord.
- Include truncated stdout/stderr and final message if available.
- Set `paused=1`.
- Do not mark task done.
- Log activity.
- Break loop.

### 10. Validation after successful Codex run

If Codex returns 0 and no clarification is detected:

```python
validation = validator.validate(project_root)
```

If validation fails:

- Post validation failure to Discord.
- Set `paused=1`.
- Do not mark task done.
- Log activity.
- Break loop.

If validation passes:

- Mark task done.
- Log activity.
- Post success message.
- Increment `completed_tasks_this_session`.

### 11. Session limit

Read:

```python
max_auto_tasks = int(os.getenv("MAX_AUTO_TASKS_PER_SESSION", "5"))
```

Count only successful cycles:

```text
Codex return code 0
no clarification marker
validator passed
task marked complete
activity logged
```

When the session limit is reached:

```text
[ORCHESTRATOR]
Session limit reached ({n} completed tasks).
Loop paused for human review.
Reply !resume to continue.
```

Set `paused=1` and break.

### 12. Discord command: `!clarify`

Command:

```text
!clarify <task_id> <clarification text>
```

Behavior:

1. Verify the task id matches the task awaiting clarification.
2. Append to `agent-orchestrator/last_prompt.md`:

```markdown
---

## Human Clarification

Task: <task_id>

<clarification text>
```

3. Clear awaiting-clarification marker.
4. Keep `paused=1`.
5. Post:

```text
Clarification added for Task {id}. Send !resume to retry.
```

### 13. Discord command: `!skip-task`

Command:

```text
!skip-task <task_id>
```

Behavior:

1. Verify the task id is current or awaiting clarification.
2. Mark the task `skipped` in `state.sqlite`.
3. Append an `ACTIVITY.md` entry if supported by the existing logger.
4. Clear awaiting-clarification marker.
5. Keep `paused=1`.
6. Post:

```text
Task {id} skipped. Send !resume to continue.
```

---

# Stage 12d Codex Implementation Prompt

Use this prompt when asking Codex to implement Stage 12d.

```text
Read docs/AGENT_ORCHESTRATOR_PLAN.md and docs/AGENT_ORCHESTRATOR_PRODUCTION_PLAN.md first.

I am implementing Stage 12d: Mode B hardening for headless Codex CLI automation.

Confirmed CLI behavior:
- Use `codex exec`, not `codex run`.
- `codex exec -` reads the initial instructions from stdin.
- `-C <DIR>` sets Codex working root.
- `-s workspace-write` sets the sandbox mode.
- `--ask-for-approval` is not available for `codex exec`; use `-c approval_policy="never"` instead.
- `-o <FILE>` writes the last Codex message to a file.
- `-m <MODEL>` is available if CODEX_MODEL is configured.

Main goal:
Enable a headless process where the orchestrator can remotely develop the project by invoking Codex CLI automatically, while requiring human intervention only for approval-required gates, clarification requests, validation failures, timeouts, phase gates, pause/resume, skip-task decisions, or session limits.

Files allowed to modify:
- agent-orchestrator/orchestrator.py
- agent-orchestrator/discord_listener.py
- agent-orchestrator/.env.example

Files allowed to inspect:
- agent-orchestrator/discord_notifier.py
- agent-orchestrator/activity_logger.py
- agent-orchestrator/validator.py
- agent-orchestrator/decision_gate.py
- agent-orchestrator/prompt_runner.py
- agent-orchestrator/task_queue_reader.py
- agent-orchestrator/context_builder.py

All other files are off-limits.

Implementation requirements:

1. Add or update CODEX_MODE=auto handling in the --run-loop implementation.

2. Before invoking Codex, read agent-orchestrator/last_prompt.md.
   If missing or empty:
   - post Discord failure
   - set paused=1
   - break the loop

3. Add prompt linting before invoking Codex.
   Required fields:
   - TASK_ID:
   - TASK_TITLE:
   - OBJECTIVE:
   - FILES_ALLOWED_TO_MODIFY:
   - FILES_ALLOWED_TO_INSPECT:
   - OUT_OF_SCOPE:
   - ACCEPTANCE_CRITERIA:
   - VALIDATION_COMMANDS:
   - STOP_CONDITIONS:

   Block vague phrases:
   - fix the issue
   - do the right thing
   - make it better
   - clean this up
   - improve the project
   - handle it
   - whatever is needed

   If lint fails:
   - do not invoke Codex
   - post [ORCHESTRATOR · PROMPT BLOCKED] to Discord
   - list issues
   - set paused=1
   - break the loop

4. Ensure generated auto-mode prompts include this instruction near the top:

   You are running in a headless automation loop.
   You must not infer missing scope.
   If the task objective, allowed modification files, acceptance criteria, or validation commands are unclear, stop without modifying files and print:

   CODEX_NEEDS_CLARIFICATION:
   <specific missing information>

   Do not make a best-effort implementation when the task contract is incomplete.

5. Invoke Codex using stdin, not a positional long prompt argument.

   Use:
   codex_cmd = [
       "codex",
       "exec",
       "-",
       "-C",
       project_root,
       "-s",
       "workspace-write",
       "-c",
       'approval_policy="never"',
       "-o",
       str(codex_last_message_path),
   ]

   Then:
   result = subprocess.run(
       codex_cmd,
       input=prompt_text,
       capture_output=True,
       text=True,
       timeout=int(os.getenv("CODEX_TIMEOUT_SECONDS", "300")),
       cwd=project_root,
   )

6. If CODEX_MODEL is set, append ["-m", CODEX_MODEL] to codex_cmd.

7. If CODEX_ENABLE_SEARCH=true, append ["--search"] to codex_cmd.

8. Add .env.example values:
   CODEX_MODE=manual
   CODEX_MODEL=
   CODEX_TIMEOUT_SECONDS=300
   MAX_AUTO_TASKS_PER_SESSION=5
   CODEX_ENABLE_SEARCH=false
   CODEX_LAST_MESSAGE_PATH=agent-orchestrator/codex_last_message.md

9. Before each Codex invocation, clear the previous codex_last_message.md if it exists.

10. After Codex exits, inspect stdout, stderr, and codex_last_message.md.

11. If subprocess times out:
   - post [ORCHESTRATOR · CODEX TIMEOUT]
   - set paused=1
   - do not mark task done
   - log activity
   - break loop

12. If output contains CODEX_NEEDS_CLARIFICATION: or obvious clarification phrases:
   - post [ORCHESTRATOR · CODEX QUESTION]
   - truncate output to 1500 chars
   - set paused=1
   - store current task id as awaiting clarification
   - do not mark task done
   - break loop

13. If returncode is non-zero:
   - post failure summary
   - set paused=1
   - do not mark task done
   - log activity
   - break loop

14. If Codex returns 0 and no clarification marker exists:
   - run validator.validate(project_root)
   - if validation fails: pause, post failure, log activity, do not mark task done
   - if validation passes: mark task done, log activity, post success, increment completed_tasks_this_session

15. Add MAX_AUTO_TASKS_PER_SESSION handling:
   - default 5
   - count only successful Codex + validator cycles
   - when reached, post session limit message, set paused=1, break loop

16. Add !clarify handling in discord_listener.py:
   Command: !clarify <task_id> <clarification text>
   Behavior:
   - verify task_id matches awaiting clarification task
   - append a clearly delimited Human Clarification block to last_prompt.md
   - clear awaiting clarification marker
   - keep paused=1
   - post "Clarification added for Task {id}. Send !resume to retry."

17. Add !skip-task handling in discord_listener.py:
   Command: !skip-task <task_id>
   Behavior:
   - verify task_id is current or awaiting clarification
   - mark task skipped in state.sqlite
   - append activity entry if supported
   - clear awaiting clarification marker
   - keep paused=1
   - post "Task {id} skipped. Send !resume to continue."

18. Keep changes narrowly scoped.
Do not modify project files outside agent-orchestrator.
Do not use danger-full-access.
Do not bypass orchestrator approval gates.
Do not mark failed, timed-out, validation-failed, prompt-blocked, or clarification-blocked tasks as done.
```

---

# Verification Plan

## Test 1 — stdin-based headless happy path

```powershell
Set-Content agent-orchestrator\last_prompt.md "Create agent-orchestrator/codex_headless_test.txt containing the text 'headless test ok'. Do not modify anything else."
$prompt = Get-Content agent-orchestrator\last_prompt.md -Raw

$prompt | codex exec - `
  -C . `
  -s workspace-write `
  -c approval_policy='"never"' `
  -o agent-orchestrator\codex_last_message.md
```

Expected:

```text
file created
final message written
no unrelated files modified
```

## Test 2 — prompt lint blocks vague prompt

```powershell
Set-Content agent-orchestrator\last_prompt.md "Fix the issue in the project. Do the right thing."
$env:CODEX_MODE="auto"
python agent-orchestrator\orchestrator.py --run-loop
```

Expected:

```text
Codex is not invoked
Discord receives PROMPT BLOCKED message
paused=1
```

## Test 3 — Codex clarification marker

Use a prompt contract with missing/unclear information but containing the required stop condition.

Expected:

```text
Codex prints CODEX_NEEDS_CLARIFICATION:
or the orchestrator detects missing prompt details before invocation
loop pauses
```

## Test 4 — timeout

```powershell
$env:CODEX_MODE="auto"
$env:CODEX_TIMEOUT_SECONDS="5"
python agent-orchestrator\orchestrator.py --run-loop
```

Expected:

```text
timeout message posted
paused=1
task not marked done
```

## Test 5 — validation failure

Create a safe task that intentionally causes validation to fail.

Expected:

```text
Codex may complete
validator fails
loop pauses
task not marked done
ACTIVITY.md records failure
```

## Test 6 — session limit

```powershell
$env:CODEX_MODE="auto"
$env:MAX_AUTO_TASKS_PER_SESSION="2"
python agent-orchestrator\orchestrator.py --run-loop
```

Expected:

```text
after 2 successful Codex + validation cycles, loop pauses
Discord posts session limit message
```

## Test 7 — !clarify

Send:

```text
!clarify <task_id> Use file X and preserve behavior Y.
```

Expected:

```text
clarification block appended to last_prompt.md
awaiting clarification marker cleared
paused remains 1
Discord says to send !resume
```

## Test 8 — !skip-task

Send:

```text
!skip-task <task_id>
```

Expected:

```text
task marked skipped
activity logged
paused remains 1
Discord says to send !resume
```

---

# Production Readiness Checklist

Before unsupervised operation:

```text
[ ] `codex exec -` stdin invocation tested successfully
[ ] `-o codex_last_message.md` tested successfully
[ ] Prompt lint blocks vague prompts
[ ] CODEX_NEEDS_CLARIFICATION marker detection tested
[ ] Timeout handling tested
[ ] Validator failure handling tested
[ ] MAX_AUTO_TASKS_PER_SESSION tested
[ ] !pause tested from phone
[ ] !resume tested from phone
[ ] !clarify tested from Discord
[ ] !skip-task tested from Discord
[ ] Phase gate approval still blocks correctly
[ ] ACTIVITY.md receives complete entries
[ ] state.sqlite records correct task status
[ ] No use of danger-full-access
[ ] No dependency on unstable/disabled feature flags
```

---

# Final Design Rule

For Mode B:

```text
Codex is the implementation subprocess.
The orchestrator is the control plane.
Discord is the human interface.
Prompt linting is the ambiguity gate.
Validation is the correctness gate.
Approval gates remain outside Codex.
```

Do not rely on Codex to ask questions after it starts. If a task is vague enough that you hope Codex will ask, the orchestrator should block it before launch.
