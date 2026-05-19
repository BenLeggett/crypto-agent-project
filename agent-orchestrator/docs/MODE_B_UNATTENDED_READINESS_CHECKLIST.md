# Mode B Unattended Readiness Checklist

Last updated: 2026-05-17

Purpose: manually verify that `CODEX_MODE=auto` is ready to run unattended as
the development orchestrator control plane.

Important boundary: this checklist does **not** approve live trading, live wallet
execution, exchange credentials, deployment changes, or production trading
capital. "Go live" here means the agent orchestrator can be left running
unattended for development automation while preserving Discord control,
deterministic validation, and human approval gates.

Do not leave Mode B unattended until every required check below is marked pass.

---

## Flow Diagram

```text
Operator starts listener + run loop
        |
        v
Discord dashboard card appears
        |
        v
Loop checks pause flag and current phase
        |
        +--> Paused? ----------------------+
        |                                  |
        | yes                              | no
        v                                  v
Wait for !resume                 Find next eligible task
                                           |
                                           v
                                 Approval gate needed?
                                           |
                         +-----------------+-----------------+
                         |                                   |
                         | yes                               | no
                         v                                   v
                 Ask Discord approval              Generate last_prompt.md
                         |                                   |
                         v                                   v
              !approve / !reject?                  Prompt contract lint
                         |                                   |
          +--------------+-------------+        +------------+------------+
          |                            |        |                         |
          | reject/timeout             |        | fail                    | pass
          v                            |        v                         v
     Pause and wait                    |   PROMPT BLOCKED          Invoke codex exec
                                       |   Pause for clarify              |
                                       |                                  v
                                       |                         Codex result captured
                                       |                                  |
                                       |          +-----------------------+----------------------+
                                       |          |                       |                      |
                                       |          | timeout/failure       | clarification        | success
                                       |          v                       v                      v
                                       |   Pause for review       Pause for clarify      Deterministic validation
                                       |                                                         |
                                       |                                     +-------------------+-------------------+
                                       |                                     |                                       |
                                       |                                     | fail                                  | pass
                                       |                                     v                                       v
                                       |                              Pause for repair                       Mark task done
                                       |                                                                             |
                                       |                                                                             v
                                       |                                                               Session limit reached?
                                       |                                                                             |
                                       |                                                           +-----------------+----------------+
                                       |                                                           |                                  |
                                       |                                                           | yes                              | no
                                       |                                                           v                                  v
                                       +---------------------------------------------------- Pause for review                 Continue loop
```

---

## Evidence Log

Create a local evidence note before starting:

```text
Date/time:
Operator:
Machine:
Branch:
Commit or git status summary before test:
Codex CLI version:
CODEX_MODE:
MAX_AUTO_TASKS_PER_SESSION:
CODEX_TIMEOUT_SECONDS:
Discord channel:
Result:
```

Recommended file:

```text
agent-orchestrator/logs/mode_b_readiness_YYYYMMDD.md
```

Do not include secrets in the evidence note.

---

## Phase 0 - Preconditions

### 0.1 Confirm clean or understood working tree

Run:

```powershell
git status --short
```

Pass:

- [ ] Every listed file is expected.
- [ ] No `.env`, secret, wallet, exchange credential, webhook URL, bot token, or
  live config credential is staged or unstaged.
- [ ] Any staged changes are intentionally part of this readiness candidate.

Fail:

- [ ] Unknown source changes exist.
- [ ] Secret-bearing files or values appear.

### 0.2 Confirm dependencies and tests

Run:

```powershell
python -m pytest agent-orchestrator
python -m py_compile agent-orchestrator/orchestrator.py agent-orchestrator/discord_listener.py agent-orchestrator/operator_events.py agent-orchestrator/prompt_runner.py
```

Pass:

- [ ] Orchestrator tests pass.
- [ ] Python compile checks pass.

### 0.3 Confirm Codex CLI is installed and authenticated

Run:

```powershell
codex --help
codex exec --help
codex features list
```

Pass:

- [ ] `codex exec` is available.
- [ ] `-C`, `-s`, `-c`, `-m`, `-o`, and stdin prompt behavior are available.
- [ ] No unsupported or dangerous flag is required.

### 0.4 Confirm local `.env` safe defaults

Inspect local `agent-orchestrator/.env`.

Pass:

- [ ] `PROJECT_ROOT=..`
- [ ] `CODEX_MODE=manual` before initial tests.
- [ ] `CODEX_TIMEOUT_SECONDS=300` or another intentional value.
- [ ] `MAX_AUTO_TASKS_PER_SESSION=1` for first unattended rehearsal.
- [ ] `CODEX_ENABLE_SEARCH=false` unless the test task genuinely needs web search.
- [ ] `CODEX_LAST_MESSAGE_PATH=agent-orchestrator/codex_last_message.md`
- [ ] No live trading, wallet, or exchange write credentials are enabled.

---

## Phase 1 - Discord Control Plane

### 1.1 Start the listener

Terminal 1:

```powershell
python agent-orchestrator/discord_listener.py
```

Pass:

- [ ] If Discord credentials are wired, the bot connects to the command channel.
- [ ] If credentials are not wired, mock stdin mode starts.
- [ ] No startup exception occurs.

### 1.2 Verify operator commands

From Discord or mock stdin, run:

```text
!status
!pause
!status
!resume
!status
!explain
```

Pass:

- [ ] `!status` returns the task dashboard/card.
- [ ] `!pause` sets paused state.
- [ ] `!resume` clears paused state.
- [ ] `!explain` returns a deterministic explanation or local model summary.
- [ ] Buttons appear only on the newest bot-owned dashboard message.
- [ ] Buttons hide while work is in flight.

### 1.3 Verify approval commands

Use a harmless test ref:

```text
!approve readiness-test-ref
!reject readiness-test-ref-2 not approved for readiness test
```

Pass:

- [ ] Approval response is recorded.
- [ ] Rejection response is recorded.
- [ ] No task is marked done by approval command alone.

---

## Phase 2 - Manual Mode Full Cycle

### 2.1 Start manual run loop

Terminal 2:

```powershell
$env:CODEX_MODE="manual"
python agent-orchestrator/orchestrator.py --run-loop
```

Pass:

- [ ] Dashboard/card shows loop started.
- [ ] A task prompt is generated.
- [ ] `agent-orchestrator/last_prompt.md` exists.
- [ ] Loop pauses after prompt generation.
- [ ] Dashboard tells the operator to review/apply `last_prompt.md`.

### 2.2 Verify prompt contract

Run:

```powershell
python -c "import sys; sys.path.insert(0, 'agent-orchestrator'); import orchestrator; text=open('agent-orchestrator/last_prompt.md', encoding='utf-8').read(); print(orchestrator.lint_codex_prompt_contract(text))"
```

Pass:

- [ ] Output is `[]`.
- [ ] `last_prompt.md` starts with `# Codex Task Contract`.
- [ ] Required fields are present:
  - [ ] `TASK_ID:`
  - [ ] `TASK_TITLE:`
  - [ ] `OBJECTIVE:`
  - [ ] `FILES_ALLOWED_TO_MODIFY:`
  - [ ] `FILES_ALLOWED_TO_INSPECT:`
  - [ ] `OUT_OF_SCOPE:`
  - [ ] `ACCEPTANCE_CRITERIA:`
  - [ ] `VALIDATION_COMMANDS:`
  - [ ] `STOP_CONDITIONS:`

### 2.3 Resume and validate

If no real task work should be applied, do this only in a disposable readiness
branch or with a harmless queued task.

From Discord:

```text
!resume
```

Pass:

- [ ] Loop wakes up.
- [ ] Deterministic validator runs.
- [ ] Failure pauses and is explained, or success marks the task done.
- [ ] Task is not marked done if validation fails.

---

## Phase 3 - Codex CLI Stdin Smoke Test

Run only after confirming Codex CLI is authenticated.

### 3.1 Save current prompt

```powershell
Copy-Item agent-orchestrator\last_prompt.md agent-orchestrator\last_prompt.readiness.bak
```

### 3.2 Run a tiny headless Codex test

```powershell
Set-Content agent-orchestrator\last_prompt.md "Create agent-orchestrator/codex_headless_test.txt containing exactly the text 'headless test ok'. Do not modify anything else."
$prompt = Get-Content agent-orchestrator\last_prompt.md -Raw
$prompt | codex exec -C . -s workspace-write -c approval_policy='"never"' -o agent-orchestrator\codex_last_message.md -
```

Pass:

- [ ] `agent-orchestrator/codex_headless_test.txt` exists.
- [ ] The file contains `headless test ok`.
- [ ] `agent-orchestrator/codex_last_message.md` exists.
- [ ] No unrelated files are modified.

### 3.3 Cleanup

```powershell
Remove-Item agent-orchestrator\codex_headless_test.txt
Move-Item -Force agent-orchestrator\last_prompt.readiness.bak agent-orchestrator\last_prompt.md
git status --short
```

Pass:

- [ ] Test file is removed.
- [ ] Original prompt is restored.
- [ ] Working tree contains only expected readiness changes.

---

## Phase 4 - Prompt Block and Clarification Flow

This verifies Codex is not invoked on vague prompts.

### 4.1 Use a disposable test branch or controlled test task

Pass:

- [ ] You are not testing against important uncommitted work.
- [ ] You can restore `last_prompt.md` after the test.

### 4.2 Force a vague prompt for local test only

Use the unit-tested path where possible. If testing manually, temporarily write:

```powershell
Copy-Item agent-orchestrator\last_prompt.md agent-orchestrator\last_prompt.readiness.bak
Set-Content agent-orchestrator\last_prompt.md "Fix the issue in the project. Do the right thing."
```

Then run prompt lint:

```powershell
python -c "import sys; sys.path.insert(0, 'agent-orchestrator'); import orchestrator; text=open('agent-orchestrator/last_prompt.md', encoding='utf-8').read(); print(orchestrator.lint_codex_prompt_contract(text))"
```

Pass:

- [ ] Output lists missing required fields.
- [ ] Output lists blocked vague phrases.

### 4.3 Restore prompt

```powershell
Move-Item -Force agent-orchestrator\last_prompt.readiness.bak agent-orchestrator\last_prompt.md
```

### 4.4 Verify clarification controls

If the dashboard shows a clarification state, use:

```text
!clarify <task_id> Use the exact file X and preserve behavior Y.
```

Or press `Clarify Task <id>` and submit the Discord modal.

Pass:

- [ ] A `Human Clarification` block is appended to `last_prompt.md`.
- [ ] Dashboard remains paused.
- [ ] Dashboard says to resume when ready.
- [ ] `!resume` retries from the clarified prompt.

---

## Phase 5 - Auto Mode Controlled Rehearsal

Start with exactly one successful auto cycle.

### 5.1 Configure conservative auto mode

In the current terminal:

```powershell
$env:CODEX_MODE="auto"
$env:MAX_AUTO_TASKS_PER_SESSION="1"
$env:CODEX_TIMEOUT_SECONDS="300"
$env:CODEX_ENABLE_SEARCH="false"
```

Pass:

- [ ] Session limit is `1`.
- [ ] Timeout is intentional.
- [ ] Search is off unless required.

### 5.2 Start auto run loop

```powershell
python agent-orchestrator/orchestrator.py --run-loop
```

Expected dashboard story:

```text
Loop started
Prompt generated
Codex running
Validation running
Task done OR paused for failure
Session limit reached after one successful task
```

Pass:

- [ ] Prompt contract lint runs before Codex.
- [ ] Codex final message file is refreshed.
- [ ] Validator runs after Codex success.
- [ ] Task is marked done only if validator passes.
- [ ] Loop pauses after one successful task.
- [ ] Discord dashboard shows session limit reached.

Fail if:

- [ ] Codex is invoked after a prompt-blocked state.
- [ ] A task is marked done after timeout, Codex failure, or validation failure.
- [ ] Buttons remain available while Codex/validation is in flight.
- [ ] Session limit is ignored.

---

## Phase 6 - Failure Handling Rehearsal

These checks can be satisfied by automated tests plus one observed manual
dashboard review. Do not create destructive repo changes for this.

### 6.1 Timeout behavior

Set a very low timeout only in a controlled test:

```powershell
$env:CODEX_MODE="auto"
$env:CODEX_TIMEOUT_SECONDS="5"
python agent-orchestrator/orchestrator.py --run-loop
```

Pass:

- [ ] Dashboard status says Codex timed out.
- [ ] Buttons show `Resume` and `Skip Task <id>`.
- [ ] Task is not marked done.
- [ ] Validation is not treated as passed.

Restore:

```powershell
$env:CODEX_TIMEOUT_SECONDS="300"
```

### 6.2 Non-zero Codex exit behavior

Pass by automated test or controlled observation:

- [ ] Dashboard status says Codex failed.
- [ ] Dashboard finding explains Codex exited with an error.
- [ ] Buttons show retry/skip path.
- [ ] Task is not marked done.

### 6.3 Validation failure behavior

Pass by automated test or controlled observation:

- [ ] Dashboard status says Failed validation.
- [ ] Finding summarizes validator errors.
- [ ] `Deep Diagnose` appears for failed tasks.
- [ ] `!explain` works when no review is in flight.
- [ ] Task remains failed until a later validation pass.

---

## Phase 7 - Skip Task Flow

Only use this on a disposable or intentionally skippable task.

From Discord:

```text
!skip-task <task_id>
```

Or press `Skip Task <id>` if the dashboard offers it.

Pass:

- [ ] Task status becomes `skipped`.
- [ ] Dashboard remains paused.
- [ ] `ACTIVITY.MD` records the skip.
- [ ] `!resume` proceeds to the next eligible task or phase gate.

---

## Phase 8 - Phase Gate Flow

Allow current phase tasks to complete or use a controlled test state.

Pass:

- [ ] Phase review starts only after mapped current-phase tasks are done or skipped.
- [ ] Dashboard shows approval required.
- [ ] `Approve <ref>` and `Reject <ref>` buttons appear.
- [ ] `!approve <ref>` advances the phase.
- [ ] `!reject <ref> <notes>` pauses the loop.
- [ ] No later phase task starts before approval.

---

## Phase 9 - Service / Unattended Runtime Rehearsal

Run the listener and loop as they will run unattended.

Options:

- Task Scheduler.
- NSSM.
- Two terminal windows for final supervised rehearsal.

Pass:

- [ ] Listener starts without a human terminal interaction.
- [ ] Run loop starts without a human terminal interaction.
- [ ] Logs are written where expected.
- [ ] Discord `!status` works from phone.
- [ ] Discord `!pause` stops the loop before the next task.
- [ ] Discord `!resume` restarts the loop.
- [ ] Restarting the listener recreates or recovers the dashboard card.
- [ ] Reboot test passes if this will run through reboot.

---

## Final Go / No-Go Decision

Mode B unattended development automation is ready only if all are true:

- [ ] Orchestrator tests pass.
- [ ] Codex CLI stdin smoke test passes.
- [ ] Manual mode full cycle passes.
- [ ] Discord dashboard accurately tells the current state.
- [ ] Buttons only show safe available actions.
- [ ] Prompt-blocked state prevents Codex invocation.
- [ ] Clarification flow works.
- [ ] Timeout flow pauses without marking done.
- [ ] Codex failure flow pauses without marking done.
- [ ] Validation failure flow pauses without marking done.
- [ ] Session limit pauses after successful auto cycles.
- [ ] Approval gates still block phase transitions and risky tasks.
- [ ] `ACTIVITY.MD` records important transitions.
- [ ] `state.sqlite` task statuses match observed behavior.
- [ ] `.env` and secrets remain untracked.
- [ ] No live trading, live wallet execution, or exchange write path is enabled.

Go:

- [ ] Set `CODEX_MODE=auto`.
- [ ] Keep `MAX_AUTO_TASKS_PER_SESSION` conservative, recommended `1` to `5`.
- [ ] Keep Discord reachable.
- [ ] Leave operator with this checklist and rollback instructions.

No-go:

- [ ] Any checklist item above fails.
- [ ] Dashboard state is confusing or stale.
- [ ] The loop marks a task done without validation passing.
- [ ] Discord pause/resume is unreliable.
- [ ] Secrets or live config appear in git status.

Rollback:

```powershell
$env:CODEX_MODE="manual"
python agent-orchestrator/orchestrator.py --status
```

From Discord:

```text
!pause
!status
```

If running as services, stop the orchestrator loop service first, then the
listener if needed.
