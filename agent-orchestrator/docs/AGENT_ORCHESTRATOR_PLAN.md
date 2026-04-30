# `docs/AGENT_ORCHESTRATOR_PLAN.md`

> **Scope:** Development orchestration layer only. This document does not modify the trading system, its configs, its risk controls, or any live execution path. All references to existing project files are read-only from the orchestrator's perspective.

---

## 1. Purpose and Boundaries

### What the orchestrator does

The agent orchestrator is a local development lifecycle assistant that sits entirely outside the trading system. Its job is to:

- Read the current project state from `docs/TASK_QUEUE.md`, `docs/PHASE_TASK_MAP.md`, and `docs/IMPLEMENTATION_PLAN.md`.
- Determine which task is next and build a minimal context pack for it.
- Route that context to the cheapest model capable of handling the job (local first, cloud only when justified).
- Generate a Codex-ready implementation prompt the developer can copy and run.
- Post a Discord notification summarizing what was generated and requesting human approval before any action is taken.
- Run post-implementation validation (lint, type checks, tests, forbidden-path checks) and summarize results.
- Append a structured record to `ACTIVITY.md` after every step.
- Enforce phase gates: the orchestrator will not generate prompts for a new phase until the current phase's exit checklist is satisfied.

### What it explicitly does NOT do

- It does not read, write, or modify exchange credentials, wallet configs, live Freqtrade configs, or anything under `configs/live/`.
- It does not trigger deployments, start Docker services, or execute trades.
- It does not modify `docs/IMPLEMENTATION_PLAN.md`, `docs/TASK_QUEUE.md`, or `docs/PHASE_TASK_MAP.md` — those remain human-owned sources of truth.
- It does not call premium cloud models for routine status checks or summaries.
- It does not run without human approval for anything that touches architecture, phase transitions, or risky file paths.
- It does not have autonomous authority to commit code or merge branches.

### How it stays isolated from the trading system

The orchestrator lives in its own directory (`agent-orchestrator/`) with its own virtual environment, config, and state database. It reads project docs as plain text files and has no import dependency on any trading-system library. It communicates with the developer exclusively through Discord messages and the local filesystem (`ACTIVITY.md`, `agent-orchestrator/state.sqlite`). It can invoke `git diff` and test runners read-only. No trading runtime path is in its dependency graph.

### Why this design is modular and reusable

Every component (model router, context builder, Discord notifier, validator, activity logger) is a standalone Python module with a clean interface. The orchestrator is project-agnostic except for the content of its `context/` directory and its prompt templates. Swapping those files out makes it usable for any repo. The task queue reader speaks a simple markdown format that can be adapted to any project's task structure.

---

## 2. Folder and File Structure

```text
agent-orchestrator/
├── README.md
├── config.example.yaml
├── .env.example
├── orchestrator.py          # main entry point and lifecycle loop
├── model_router.py          # tier selection and fallback logic
├── local_llm_client.py      # LM Studio OpenAI-compatible client
├── cloud_llm_client.py      # OpenAI / Anthropic cloud client
├── context_builder.py       # assembles minimal context packs per task
├── task_queue_reader.py     # parses TASK_QUEUE.md and PHASE_TASK_MAP.md
├── prompt_runner.py         # renders prompt templates with context
├── validator.py             # runs lint, tests, forbidden-path checks
├── discord_notifier.py      # webhook-based Discord integration
├── decision_gate.py         # blocks progress until human approval received
├── activity_logger.py       # appends structured records to ACTIVITY.md
├── state.sqlite             # task state, run history, approval records
├── prompts/
│   ├── status_summary.md        # what is the current project state?
│   ├── run_next_task.md         # generate a Codex prompt for the next task
│   ├── phase_review.md          # is this phase ready to exit?
│   ├── risk_review.md           # does this task touch risky paths?
│   └── failed_task_diagnosis.md # why did this task fail and what should change?
└── context/
    ├── project_summary.md       # one-page project purpose and constraints (human-maintained)
    ├── current_phase.md         # current phase, active tasks, exit criteria (auto-updated)
    ├── architecture_rules.md    # condensed red lines from ARCHITECTURE.md (human-maintained)
    └── decision_log.md          # record of gate decisions and escalations (auto-appended)
```

**Assumption:** The orchestrator directory lives at the repo root alongside `docs/`, `apps/`, `libs/`, etc. It is not a Python package inside `libs/` or `apps/` — it is a separate tool that happens to share the same repo.

---

## 3. Core Agent Workflow

```
[orchestrator.py starts]
        │
        ▼
[task_queue_reader.py]
  Read TASK_QUEUE.md + PHASE_TASK_MAP.md
  Determine: current phase, active task, done criteria, dependencies
        │
        ▼
[context_builder.py]
  Assemble minimal context pack:
    - project_summary.md (always included)
    - current_phase.md
    - architecture_rules.md
    - task-specific snippets (relevant file paths, schemas, prior failures)
    - recent ACTIVITY.md entries (last 5)
  Estimate token count; trim if over budget
        │
        ▼
[model_router.py]
  Select tier based on task type:
    status summary        → local_low
    git diff summary      → local_low
    task parsing          → local_low
    prompt assembly       → none (string interpolation; no model call)
    failed task diagnosis → cloud_high
    phase review          → cloud_high
    architecture review   → cloud_extra_high
  Check: is local LLM available? If not, escalate to next tier.
        │
        ▼
[prompt_runner.py]
  Render prompt template with context pack
  Call selected model (local_llm_client or cloud_llm_client)
  Receive: Codex prompt OR status summary OR review verdict
        │
        ▼
[decision_gate.py]
  Is approval required for this step? (see §7)
  If YES:
    → discord_notifier.py: post message with payload + approve/reject options
    → poll state.sqlite for human response (timeout configurable)
    → if rejected: log to decision_log.md, stop, notify
    → if approved: continue
  If NO:
    → continue directly
        │
        ▼
[validator.py]  ← runs AFTER developer has applied the Codex output
  git status / git diff summary
  run: make lint, make typecheck, make test (scoped to affected paths)
  check: forbidden paths not modified
  check: no secrets in diff
  check: no live config touched
  output: pass / fail + summary
        │
        ▼
[activity_logger.py]
  Append structured record to ACTIVITY.md:
    timestamp, run_id, phase, task_id, model_tier, action, outcome, notes
  Update state.sqlite: task status, approval record, model usage
        │
        ▼
[discord_notifier.py]
  Post outcome summary to Discord:
    phase, task, model used, validation result, next recommended action
        │
        ▼
[Phase gate check]
  If task marked done and all phase tasks complete:
    → load phase_review.md prompt
    → run cloud_high model review
    → require human approval before advancing phase
  Else:
    → loop to next task
```

---

## 4. Local LLM Setup (LM Studio Focus)

### Installation

1. Download LM Studio from [lmstudio.ai](https://lmstudio.ai) — available for macOS, Windows, and Linux (beta).
2. Open LM Studio → navigate to the **Discover** tab → search for and download a model (see recommended sizes below).
3. Load the model via the **Chat** tab to confirm it runs.
4. Enable the local server: **Local Server** tab → click **Start Server**. Default port is `1234`.
5. LM Studio exposes an OpenAI-compatible API at `http://localhost:1234/v1`. The `local_llm_client.py` will use this endpoint.

### Recommended model sizes for a normal developer laptop (8–16 GB RAM)

| Use case | Model size | Example |
|---|---|---|
| Status summaries, diff summaries | 3B–7B Q4 | Mistral 7B Instruct Q4, Qwen2.5 3B |
| Task parsing, prompt drafting | 7B–13B Q4 | Llama 3.1 8B Instruct Q4 |
| Phase reviews (stretch, may be slow) | 13B Q4 | Mistral Nemo 12B |

**Assumption:** Developer has at least 16 GB RAM. If RAM is 8 GB, limit to 7B Q4 models and route anything larger to cloud.

### `.env` configuration

```dotenv
# LM Studio
LOCAL_LLM_BASE_URL=http://localhost:1234/v1
LOCAL_LLM_API_KEY=lm-studio   # placeholder; LM Studio ignores this but the client requires it
LOCAL_LLM_LOW_MODEL=mistral-7b-instruct
LOCAL_LLM_MEDIUM_MODEL=llama-3.1-8b-instruct

# Cloud fallback
OPENAI_API_KEY=sk-...          # or ANTHROPIC_API_KEY
CLOUD_HIGH_MODEL=gpt-4o-mini
CLOUD_EXTRA_HIGH_MODEL=gpt-4o  # or claude-opus-4

# Discord
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

# Orchestrator
ORCHESTRATOR_APPROVAL_TIMEOUT_SECONDS=3600
ORCHESTRATOR_MAX_CONTEXT_TOKENS=4096
PROJECT_ROOT=..                # relative to agent-orchestrator/
```

### When to use local vs cloud

Use **local** when: the task is summarization, status reading, parsing structured markdown, or generating a first-draft Codex prompt for a well-understood task.

Use **cloud** when: the task involves diagnosis of a test failure, architectural review, cross-cutting risk assessment, or the local model fails to produce a usable output after one retry.

### Graceful fallback design

`model_router.py` will:
1. Ping `LOCAL_LLM_BASE_URL/v1/models` with a 2-second timeout.
2. If the ping fails or the model is not loaded, log a warning and escalate to the next tier automatically.
3. Never block the workflow waiting for a local model to load — escalate immediately.
4. Log every escalation to `state.sqlite` so usage patterns can be reviewed.

---

## 5. Model Routing Strategy

### Tiers

| Tier | Provider | When available | Cost profile |
|---|---|---|---|
| `local_low` | LM Studio 3B–7B | LM Studio running locally | Free |
| `local_medium` | LM Studio 7B–13B | LM Studio running locally | Free |
| `cloud_high` | OpenAI gpt-4o-mini or Anthropic Haiku | Always (requires API key) | Low |
| `cloud_extra_high` | OpenAI gpt-4o or Anthropic Sonnet/Opus | Always (requires API key) | High |

### Task-to-tier mapping

| Task type | Default tier | Escalation trigger |
|---|---|---|
| Status summary | `local_low` | Local unavailable |
| Git diff summary | `local_low` | Local unavailable |
| ACTIVITY.md append draft | `local_low` | Local unavailable |
| Task parsing from TASK_QUEUE.md | `local_low` | Local unavailable |
| Codex prompt assembly (routine task) | none — string interpolation only | N/A; see note below |
| Failed task diagnosis | `cloud_high` | Always at this tier |
| Phase exit review | `cloud_high` | Human requests extra review → `cloud_extra_high` |
| Architecture or risk rule review | `cloud_extra_high` | Always at this tier; requires human approval gate |
| Decision log synthesis | `local_medium` | Local unavailable |

> **Note on Codex prompt assembly:** `prompts/run_next_task.md` is a fixed canonical template (your battle-tested task implementation prompt). The orchestrator does not generate this prompt via a model — it extracts the current task's text from `TASK_QUEUE.md` and injects it into the `{task_context}` placeholder using string interpolation only. No model call is needed. The intelligence is already in the template.

### Escalation rules

The router escalates automatically when:
- Local LLM is unreachable (ping fails).
- Output from local model fails a basic format/schema check (e.g., Codex prompt is empty or malformed).
- The task is marked `risky` in the gate check (touches `libs/risk/`, `apps/supervisor/`, or any path in `configs/live/`).
- The model's estimated token requirement exceeds the local model's configured context window.
- The user sends a `!escalate` command in Discord.

Escalation is always logged in `decision_log.md` with the reason.

---

## 6. Context Management Strategy

### Principle: assemble only what the model needs for this task

The orchestrator never dumps entire files into the context. It builds a **context pack** — a small, task-specific document assembled by `context_builder.py`.

### Standard context pack layers (in order of inclusion priority)

1. **Project summary** (`context/project_summary.md`) — always included; max 300 tokens. Describes the project purpose, tech stack, and hard constraints.
2. **Current phase summary** (`context/current_phase.md`) — always included; max 200 tokens. Current phase name, active task ID, done criteria.
3. **Architecture rules** (`context/architecture_rules.md`) — always included; max 300 tokens. The red lines from ARCHITECTURE.md condensed to bullet points.
4. **Task-specific snippet** — the full text of the active task from `TASK_QUEUE.md` plus its listed dependencies. Max 400 tokens.
5. **Recent activity** — last 3–5 entries from `ACTIVITY.md`. Max 300 tokens. Omitted for first-run sessions.
6. **Diff summary** — a `git diff --stat` output (not full diff) scoped to files relevant to the task. Max 200 tokens. Included only when validating.
7. **Decision log tail** — last 2 relevant entries from `decision_log.md`. Max 200 tokens. Included only for phase review or diagnosis tasks.

**Total budget per context pack: 4096 tokens by default.** This fits comfortably in local 7B models and keeps cloud costs low.

### Token efficiency rules

- Never include full file contents when a summary or excerpt will do.
- Strip all markdown headers from included files; use plain text for context packs.
- Use `--stat` not `--patch` for diff summaries unless the diagnosis prompt specifically needs the patch.
- Archive old `ACTIVITY.md` entries (> 30 days) to a separate file so the tail stays short.
- For Codex prompt assembly, include only the active task's text from `TASK_QUEUE.md` — this is the `{task_context}` injected into `run_next_task.md`. No model call is made; the template is the prompt.

---

## 7. Human-in-the-Loop Design

### Approval required (blocks progress until explicit human `!approve`)

| Gate | Trigger |
|---|---|
| Phase transition | All tasks in current phase are marked done; orchestrator requests phase exit review |
| Risky file modification | Task output touches `libs/risk/`, `apps/supervisor/`, `freqtrade/`, or `configs/live/` |
| Architecture change | Task involves modifying `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, or `TASK_QUEUE.md` |
| Retry after second failure | A task has failed validation twice; orchestrator proposes a revised approach |
| Cloud extra-high model use | Any call to `cloud_extra_high` tier requires approval before the API call |
| Automated Codex trigger | Mode B (§9): orchestrator is about to invoke Codex CLI directly |
| Committing changes | Orchestrator generates a commit message; human reviews and commits manually |

### No approval required (orchestrator proceeds automatically)

- Generating a status summary.
- Drafting a Codex prompt for a routine, non-risky task.
- Appending to `ACTIVITY.md`.
- Posting a Discord status update.
- Running lint/typecheck/test validation (read-only).
- First failure retry (one automatic retry is allowed; second failure triggers the approval gate above).

### Approval expiry

If no approval is received within `ORCHESTRATOR_APPROVAL_TIMEOUT_SECONDS` (default 3600), the orchestrator pauses and posts a reminder. It does not proceed or self-approve.

---

## 8. Discord Integration Plan

### Phase 1: Webhook only (start here)

1. Open Discord → server settings → Integrations → Webhooks → New Webhook.
2. Choose a channel (e.g., `#dev-orchestrator`).
3. Copy the webhook URL → add to `.env` as `DISCORD_WEBHOOK_URL`.
4. `discord_notifier.py` POSTs JSON payloads to this URL. No bot permissions needed.

### Phase 2: Optional bot (later)

If you want two-way command handling (receiving `!approve`, `!reject`, etc. as messages), add a Discord bot via the Developer Portal. This is not required to start. In the interim, the developer types commands in the Discord channel and the orchestrator polls `state.sqlite` where a lightweight listener (or manual entry) records the decision.

**Simplest interim approach:** The orchestrator posts a message with instructions like "Reply `!approve TASK-22` to continue." The developer types the command. A minimal `discord_listener.py` (single polling loop via Discord bot token) watches for replies and writes to `state.sqlite`. This can be wired later.

### Message format

**Status update:**
```
[ORCHESTRATOR] Phase 3 · Task 12: Implement regime filter module
Status: Codex prompt generated ✅
Model used: local_medium (llama-3.1-8b)
Validation: pending (awaiting developer to apply prompt)
Next: run `make test` and post results
```

**Approval request:**
```
[ORCHESTRATOR · APPROVAL REQUIRED] Phase 3 → Phase 4 transition
Phase 3 exit criteria reviewed by: cloud_high (gpt-4o-mini)
Verdict: All 7 tasks marked done. Tests passing. Criteria met.
Action required: reply `!approve phase-3-exit` to advance or `!reject` with notes.
Timeout: 60 minutes
```

**Failure notification:**
```
[ORCHESTRATOR · FAILURE] Task 16: Add strategy unit tests
Validation failed: 3 tests failing in test_strategy_regime.py
Model diagnosis: cloud_high (gpt-4o-mini)
Summary: regime.py does not handle missing candle edge case (see ACTIVITY.md run 0042)
Action: Review diagnosis → apply fix → run `!retry TASK-16`
```

### Commands (typed in Discord channel)

| Command | Action |
|---|---|
| `!status` | Post current phase, active task, last 3 activity entries |
| `!next` | Show what the next task is and its dependencies |
| `!run-next` | Generate Codex prompt for next task (requires no prior pending approval) |
| `!review-phase` | Trigger phase exit review for current phase |
| `!pause` | Pause orchestrator (no new actions until `!resume`) |
| `!resume` | Resume from paused state |
| `!approve <ref>` | Approve a pending gate (phase transition, risky task, etc.) |
| `!reject <ref> <notes>` | Reject a pending gate; notes are appended to `decision_log.md` |
| `!escalate` | Force escalation of current task to next model tier |

---

## 9. Codex Integration Plan

### Mode A — Recommended starting point

The orchestrator generates a fully rendered Codex prompt and posts it to Discord. The developer copies the prompt, opens Codex (or the Claude.ai Projects interface), pastes it, reviews the output, and applies the changes manually.

**Why start here:** Zero automation risk. The developer stays in the loop for every change. The orchestrator's value is context assembly, model routing, and tracking — not automation.

The prompt is also written to `agent-orchestrator/last_prompt.md` for easy retrieval.

### Mode B — Optional automation (add later)

The orchestrator invokes the Codex CLI directly:
```bash
codex run --prompt-file agent-orchestrator/last_prompt.md --output-dir .
```

This requires:
1. Codex CLI installed and authenticated.
2. Human approval gate satisfied before every invocation (§7).
3. A dry-run flag option: `codex run --dry-run` to preview what Codex would do without applying changes.
4. Post-invocation validation (§10) runs automatically.

### Transition from A to B

Move to Mode B only after:
- At least 3 full phases have been completed successfully in Mode A.
- You trust the orchestrator's prompt quality and validation coverage.
- You have confirmed the forbidden-path checks work reliably.

A config flag in `config.example.yaml` controls the mode: `codex_mode: manual | auto`.

---

## 10. Validation and Safety

`validator.py` runs the following checks after a task's Codex output has been applied:

| Check | Command | Failure behavior |
|---|---|---|
| Git status | `git status --short` | Log untracked/unexpected files |
| Git diff summary | `git diff --stat HEAD` | Included in activity log |
| Lint | `make lint` (ruff or flake8) | Block task completion |
| Type check | `make typecheck` (mypy or pyright) | Block task completion |
| Tests (scoped) | `make test` or `pytest <affected_paths>` | Block task completion |
| Forbidden path check | Compare diff paths against blocklist | Block + require human approval |
| Secrets check | `git diff HEAD \| grep -iE 'api_key\|secret\|password\|token'` | Block + alert immediately |
| No deployment trigger | Check diff for Dockerfile, CI pipeline changes | Warn + require human approval |
| No trading module touch | Check diff for paths in `freqtrade/`, `configs/live/` | Block + require human approval |

**Forbidden path blocklist** (hardcoded in `validator.py`):
```python
FORBIDDEN_PATHS = [
    "configs/live/",
    "freqtrade/user_data/config.live.json",
    ".env",
]
```

Any diff touching these paths triggers the human approval gate regardless of task type.

---

## 11. State and Logging

### `state.sqlite`

Three tables:

**`tasks`** — mirrors `TASK_QUEUE.md` with added status fields:
```
task_id, phase, title, status (pending|in_progress|done|failed|skipped), attempts, last_run_id, notes
```

**`runs`** — one row per orchestrator invocation:
```
run_id, timestamp, task_id, model_tier, model_name, action, outcome, prompt_tokens, completion_tokens, cost_estimate_usd
```

**`approvals`** — gate decisions:
```
approval_id, run_id, gate_type, ref, requested_at, decided_at, decision (approved|rejected), notes
```

### `ACTIVITY.md`

Append-only. One entry per orchestrator action:

```markdown
## [2025-01-15 14:32:07] Run 0042 · Phase 3 · Task 12

**Action:** Codex prompt generated  
**Model:** local_medium (llama-3.1-8b-instruct) — fallback from local_low (unavailable)  
**Outcome:** Prompt written to `agent-orchestrator/last_prompt.md`  
**Validation:** Not yet run (Mode A — awaiting developer)  
**Notes:** Context pack was 1,842 tokens. Escalated tier because diff summary included 3 files.

---
```

### `context/decision_log.md`

Human-readable log of every gate decision:

```markdown
## [2025-01-15 14:45:00] Gate: Phase 3 → Phase 4 transition
- Requested by: orchestrator (run 0047)
- Reviewed by: cloud_high (gpt-4o-mini)
- Decision: APPROVED by human (!approve phase-3-exit)
- Notes: All tasks done. Tests passing.

---

## [2025-01-15 16:02:00] Gate: Task 24 (Freqtrade adapter) — risky path
- Requested by: orchestrator (run 0051)
- Files flagged: freqtrade/user_data/strategies/regime_breakout_strategy.py
- Decision: APPROVED by human (!approve task-24-risky)
- Notes: Developer confirmed changes are adapter-only, no live config touched.
```

---

## 12. Implementation Sequence

### Stage 1: Structure and config

**Objective:** Create the `agent-orchestrator/` directory, install dependencies, and wire the config/env system.

**Files touched:** `agent-orchestrator/` (entire directory scaffold), `agent-orchestrator/config.example.yaml`, `agent-orchestrator/.env.example`, `agent-orchestrator/README.md`

**Model tier:** None (pure scaffolding)

**Acceptance criteria:**
- Directory exists with all files listed in §2.
- `python orchestrator.py --help` runs without errors.
- `.env.example` documents every required variable.
- `README.md` explains how to install and configure.

**Codex prompt:**
```
Create the directory agent-orchestrator/ at the repo root with the following structure and stub files.

Files to create:
- agent-orchestrator/README.md: brief description of the orchestrator, setup steps, usage
- agent-orchestrator/config.example.yaml: all config keys with comments explaining each
- agent-orchestrator/.env.example: all required env vars with placeholder values and comments
- agent-orchestrator/orchestrator.py: main entry point; parse CLI args (--task, --status, --validate, --phase-review); load config from .env; print "Orchestrator ready" for now
- agent-orchestrator/model_router.py: stub; define ModelTier enum (LOCAL_LOW, LOCAL_MEDIUM, CLOUD_HIGH, CLOUD_EXTRA_HIGH); define route(task_type: str) -> ModelTier stub
- agent-orchestrator/local_llm_client.py: stub; define complete(prompt: str, model: str, base_url: str) -> str using requests to POST to base_url/v1/chat/completions
- agent-orchestrator/cloud_llm_client.py: stub; define complete(prompt: str, model: str, api_key: str) -> str using openai package
- agent-orchestrator/context_builder.py: stub; define build_context(task_id: str, project_root: str) -> str
- agent-orchestrator/task_queue_reader.py: stub; define read_task(task_id: str, queue_path: str) -> dict
- agent-orchestrator/prompt_runner.py: stub; define run_prompt(template_path: str, context: str) -> str
- agent-orchestrator/validator.py: stub; define validate(project_root: str) -> dict with keys passed, errors
- agent-orchestrator/discord_notifier.py: stub; define notify(webhook_url: str, message: str) -> None using requests
- agent-orchestrator/decision_gate.py: stub; define check_gate(gate_type: str, ref: str, db_path: str) -> bool
- agent-orchestrator/activity_logger.py: stub; define log_activity(record: dict, activity_path: str) -> None

Do NOT modify any file outside agent-orchestrator/.
Do NOT import from any trading system library (apps/, libs/, freqtrade/).
Use only: python standard library, requests, openai, pyyaml, python-dotenv.
```

---

### Stage 2: Local LLM client

**Objective:** Implement `local_llm_client.py` with LM Studio connectivity, health check, and graceful failure.

**Files touched:** `agent-orchestrator/local_llm_client.py`

**Model tier:** None (implementation task)

**Acceptance criteria:**
- `ping(base_url)` returns True if LM Studio is reachable, False otherwise (2-second timeout).
- `complete(prompt, model, base_url)` sends a chat completion request and returns the response text.
- On connection error, raises `LocalLLMUnavailable` exception (do not swallow the error).
- Manual test: with LM Studio running, `python -c "from local_llm_client import complete; print(complete('Say hello', 'mistral-7b', 'http://localhost:1234'))"` returns a response.

**Codex prompt:**
```
Implement agent-orchestrator/local_llm_client.py.

Requirements:
1. Define exception: LocalLLMUnavailable(Exception)
2. Define ping(base_url: str, timeout: int = 2) -> bool
   - GET base_url/v1/models
   - Return True if status 200, False on any error or timeout
3. Define complete(prompt: str, model: str, base_url: str, max_tokens: int = 1024, temperature: float = 0.2) -> str
   - POST to base_url/v1/chat/completions
   - Payload: {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": max_tokens, "temperature": temperature}
   - Return response["choices"][0]["message"]["content"]
   - Raise LocalLLMUnavailable if connection fails
   - Raise ValueError if response is malformed
4. Use only: requests, standard library. No LangChain or LlamaIndex.
5. Add a __main__ block for manual testing:
   - Reads base_url from env LOCAL_LLM_BASE_URL (default http://localhost:1234)
   - Pings, then sends "Say hello in one sentence."
   - Prints result

Do NOT modify any other file.
```

---

### Stage 3: Model router

**Objective:** Implement `model_router.py` with tier selection, fallback logic, and escalation rules.

**Files touched:** `agent-orchestrator/model_router.py`

**Model tier:** None

**Acceptance criteria:**
- `route(task_type, local_available)` returns the correct `ModelTier` for each task type.
- When `local_available=False`, any local tier escalates to the next tier automatically.
- Risky task types (defined in a `RISKY_TASK_TYPES` set) always route to at least `cloud_high`.

**Codex prompt:**
```
Implement agent-orchestrator/model_router.py.

Requirements:
1. Define ModelTier enum: LOCAL_LOW, LOCAL_MEDIUM, CLOUD_HIGH, CLOUD_EXTRA_HIGH
2. Define TASK_TIER_MAP: dict[str, ModelTier] mapping these task types to their default tier:
   - "status_summary" → LOCAL_LOW
   - "diff_summary" → LOCAL_LOW
   - "activity_log_draft" → LOCAL_LOW
   - "task_parsing" → LOCAL_MEDIUM
   - "codex_prompt_generation" → LOCAL_MEDIUM
   - "failed_task_diagnosis" → CLOUD_HIGH
   - "phase_review" → CLOUD_HIGH
   - "architecture_review" → CLOUD_EXTRA_HIGH
   - "risk_review" → CLOUD_EXTRA_HIGH
3. Define RISKY_TASK_TYPES: set = {"architecture_review", "risk_review"}
4. Define route(task_type: str, local_available: bool = True) -> ModelTier
   - Look up TASK_TIER_MAP (default CLOUD_HIGH if not found)
   - If result is LOCAL_* and local_available is False, escalate: LOCAL_LOW → CLOUD_HIGH, LOCAL_MEDIUM → CLOUD_HIGH
   - If task_type in RISKY_TASK_TYPES, always return at least CLOUD_HIGH
   - Return final ModelTier
5. Define escalate(current: ModelTier) -> ModelTier
   - Returns the next tier up, or CLOUD_EXTRA_HIGH if already at top

Do NOT modify any other file.
```

---

### Stage 4: Context builder

**Objective:** Implement `context_builder.py` to assemble minimal context packs from project files.

**Files touched:** `agent-orchestrator/context_builder.py`, `agent-orchestrator/task_queue_reader.py`

**Model tier:** None

**Acceptance criteria:**
- `build_context(task_id, project_root)` returns a string under `max_tokens` (estimated by word count × 1.3).
- `read_task(task_id, queue_path)` correctly parses the task title, goal, files, and done criteria from `TASK_QUEUE.md`.
- Context pack always includes project_summary, current_phase, architecture_rules, and the active task.

**Codex prompt:**
```
Implement agent-orchestrator/task_queue_reader.py and agent-orchestrator/context_builder.py.

task_queue_reader.py requirements:
1. Define read_task(task_id: str, queue_path: str) -> dict
   - Parse TASK_QUEUE.md (markdown format: ## N. Title followed by bullet fields)
   - Return: {id, title, goal, files, dependencies, done_criteria}
   - Raise TaskNotFound if task_id not in file
2. Define list_tasks(queue_path: str) -> list[dict]
   - Return all tasks in order with id, title, dependencies (as list of int)

context_builder.py requirements:
1. Define MAX_CONTEXT_TOKENS = 4096 (configurable from env ORCHESTRATOR_MAX_CONTEXT_TOKENS)
2. Define estimate_tokens(text: str) -> int: return int(len(text.split()) * 1.3)
3. Define build_context(task_id: str, project_root: str, include_diff: bool = False) -> str
   - Read and include (in order, trimming if over budget):
     a. agent-orchestrator/context/project_summary.md (max 300 tokens)
     b. agent-orchestrator/context/current_phase.md (max 200 tokens)
     c. agent-orchestrator/context/architecture_rules.md (max 300 tokens)
     d. Task from TASK_QUEUE.md matching task_id (max 400 tokens)
     e. Last 5 lines of ACTIVITY.md if it exists (max 300 tokens)
     f. If include_diff: run subprocess git diff --stat HEAD (max 200 tokens)
   - Join sections with --- separators
   - Return assembled string; log warning if truncated
4. Use only: standard library, pathlib, subprocess.

Do NOT modify any other file.
Do NOT import from apps/, libs/, or freqtrade/.
```

---

### Stage 5: Read-only status command

**Objective:** Wire `orchestrator.py --status` to print current phase, active task, and last 3 activity entries.

**Files touched:** `agent-orchestrator/orchestrator.py`, `agent-orchestrator/state.sqlite` (initialized here)

**Model tier:** `local_low` (for summarizing the status if LLM is available) or plain text output

**Acceptance criteria:**
- `python orchestrator.py --status` prints: current phase name, active task ID and title, last 3 `ACTIVITY.md` entries (or "No activity yet").
- `state.sqlite` is created with the three tables defined in §11 if it does not exist.
- No model call is required for `--status`; it reads files and db only.

**Codex prompt:**
```
Implement the --status command in agent-orchestrator/orchestrator.py.

Requirements:
1. On startup, load .env from agent-orchestrator/.env using python-dotenv
2. Initialize state.sqlite with tables: tasks, runs, approvals (schemas from AGENT_ORCHESTRATOR_PLAN.md §11)
3. --status command:
   a. Read docs/PHASE_TASK_MAP.md to find the current phase (first phase whose tasks are not all marked done in state.sqlite; or Phase 1 if db is empty)
   b. Read docs/TASK_QUEUE.md to find the first non-done task in that phase
   c. Print formatted output:
      === ORCHESTRATOR STATUS ===
      Phase: <phase name>
      Active task: <task_id> — <task title>
      Done criteria: <done criteria text>
      
      Recent activity:
      <last 3 ACTIVITY.md entries, or "No activity yet">
   d. Exit 0

Do NOT call any model.
Do NOT modify any file outside agent-orchestrator/.
Do NOT read configs/live/, freqtrade/, or .env at repo root.
```

---

### Stage 6: Discord webhook notifier

**Objective:** Implement `discord_notifier.py` with webhook POST and message formatting.

**Files touched:** `agent-orchestrator/discord_notifier.py`

**Model tier:** None

**Acceptance criteria:**
- `notify(webhook_url, message)` POSTs to Discord and succeeds with a real webhook URL.
- `notify(webhook_url=None, message)` logs to stdout instead (mock mode for development without webhook).
- Message format matches the templates in §8.
- On HTTP error, logs the error and does not raise (delivery failure must not block the orchestrator).

**Codex prompt:**
```
Implement agent-orchestrator/discord_notifier.py.

Requirements:
1. Define format_status(phase, task_id, task_title, model_used, outcome, next_action) -> str
   Returns a Discord-formatted message matching this template:
   [ORCHESTRATOR] {phase} · Task {task_id}: {task_title}
   Status: {outcome}
   Model used: {model_used}
   Next: {next_action}

2. Define format_approval_request(gate_type, ref, verdict, timeout_minutes) -> str
   Returns:
   [ORCHESTRATOR · APPROVAL REQUIRED] {gate_type}
   Verdict: {verdict}
   Action required: reply `!approve {ref}` or `!reject {ref} <notes>`
   Timeout: {timeout_minutes} minutes

3. Define notify(message: str, webhook_url: str | None = None) -> None
   - If webhook_url is None or empty: print message to stdout with prefix [DISCORD-MOCK]
   - Otherwise: POST {"content": message} to webhook_url
   - On any requests error: log error to stderr, do not raise

4. Use only: requests, standard library.

Do NOT modify any other file.
```

---

### Stage 7: Activity logger

**Objective:** Implement `activity_logger.py` to append structured records to `ACTIVITY.md` and `state.sqlite`.

**Files touched:** `agent-orchestrator/activity_logger.py`

**Model tier:** None

**Acceptance criteria:**
- `log_activity(record)` appends a formatted entry to `ACTIVITY.md` matching the format in §11.
- `log_run(record)` inserts a row into `state.sqlite` `runs` table.
- Both are idempotent (a second call with the same `run_id` updates rather than duplicates).

**Codex prompt:**
```
Implement agent-orchestrator/activity_logger.py.

Requirements:
1. Define log_activity(record: dict, activity_path: str = "ACTIVITY.md") -> None
   - record keys: run_id, timestamp (ISO8601), phase, task_id, action, model_tier, model_name, outcome, notes
   - Append to activity_path using this format (see AGENT_ORCHESTRATOR_PLAN.md §11 for template)
   - Create file if it does not exist

2. Define log_run(record: dict, db_path: str = "agent-orchestrator/state.sqlite") -> None
   - INSERT OR REPLACE into runs table
   - record keys match the runs table schema from §11

3. Use only: standard library, sqlite3, pathlib.
4. Both functions must be safe to call in parallel (use WAL mode for sqlite).

Do NOT modify any other file.
```

---

### Stage 8: Codex prompt assembler

**Objective:** Implement `prompt_runner.py` to inject task context into fixed prompt templates. For `run_next_task.md`, no model call is made — the template is the prompt. For model-backed prompts (phase review, diagnosis, risk review), call the appropriate tier.

**Files touched:** `agent-orchestrator/prompt_runner.py`, `agent-orchestrator/prompts/run_next_task.md`

**Model tier:** None for task prompt assembly (string interpolation only). `cloud_high` / `cloud_extra_high` for model-backed templates (phase review, diagnosis).

**Acceptance criteria:**
- `assemble_prompt(template_path, context)` reads the template, replaces `{task_context}` with the injected context string, writes the result to `last_prompt.md`, and returns it — no model call.
- `run_model_prompt(template_path, context, model_tier, config)` does the same injection then calls the appropriate model client, for templates that require a model response (phase review, diagnosis, risk review).
- `run_next_task.md` contains the canonical task implementation prompt verbatim, with `{task_context}` as the only placeholder.
- Output is written to `agent-orchestrator/last_prompt.md`.
- A run record is written to `state.sqlite`.

**Codex prompt:**
```
Implement agent-orchestrator/prompt_runner.py and agent-orchestrator/prompts/run_next_task.md.

prompt_runner.py requirements:

1. Define assemble_prompt(template_path: str, task_context: str, output_path: str = "agent-orchestrator/last_prompt.md") -> str
   - Read template from template_path
   - Replace {task_context} placeholder with task_context string
   - Write result to output_path (overwrite)
   - Return rendered string
   - Do NOT call any model

2. Define run_model_prompt(template_path: str, context: str, model_tier: ModelTier, config: dict) -> str
   - Read template from template_path
   - Replace {task_context} placeholder with context string
   - Based on model_tier, call local_llm_client.complete() or cloud_llm_client.complete()
   - Return model response string
   - Config dict keys used: LOCAL_LLM_BASE_URL, LOCAL_LLM_LOW_MODEL, LOCAL_LLM_MEDIUM_MODEL,
     OPENAI_API_KEY, CLOUD_HIGH_MODEL, CLOUD_EXTRA_HIGH_MODEL

prompts/run_next_task.md:
Write the following content VERBATIM — do not paraphrase or restructure:

---
Read AGENTS.md and the relevant docs first.

{task_context}

Implement the next dependency-ordered task only.

If any dependency task appears incomplete based on the docs, stop and report the gap rather than proceeding.

Requirements:
* preserve the staged autonomous architecture
* preserve the deterministic risk governor as authoritative over hard constraints
* preserve paper-trading-first rollout
* do not assume live wallet execution is approved yet
* implement everything possible without secrets
* where secrets would normally be needed, add interfaces, env placeholders, mocks, tests, and manual wiring notes
* keep the patch narrowly scoped
* update docs if setup or behavior changes

Before coding:
1. restate the task
2. list files to change
3. identify any manual wiring boundaries
4. provide a short plan

Then implement the task and provide:
* summary of changes
* tests added or updated
* docs updated
* any entries appended to docs/MANUAL_WIRING_CHECKLIST.md
---

Do NOT modify any other file.
Do NOT alter the prompt text in run_next_task.md — it must be preserved exactly as specified above.
```

---

### Stage 9: Validator

**Objective:** Implement `validator.py` with all checks defined in §10.

**Files touched:** `agent-orchestrator/validator.py`

**Model tier:** None (subprocess calls only)

**Acceptance criteria:**
- `validate(project_root)` returns `{"passed": bool, "errors": list[str], "warnings": list[str], "diff_summary": str}`.
- Forbidden path check catches any diff touching `FORBIDDEN_PATHS`.
- Secrets check catches common patterns in diff output.
- All subprocess calls have a 60-second timeout.

**Codex prompt:**
```
Implement agent-orchestrator/validator.py.

Requirements:
1. Define FORBIDDEN_PATHS = ["configs/live/", "freqtrade/user_data/config.live.json", ".env"]
2. Define SECRETS_PATTERNS = ["api_key", "api_secret", "password", "token", "passphrase"] (case-insensitive)
3. Define validate(project_root: str) -> dict
   Returns: {passed: bool, errors: list[str], warnings: list[str], diff_summary: str}
   
   Run these checks in order (stop on first error for forbidden/secrets, continue others):
   a. git diff --stat HEAD (capture output as diff_summary)
   b. Check diff output for FORBIDDEN_PATHS → add to errors if found
   c. Check git diff HEAD (full patch) for SECRETS_PATTERNS → add to errors if found
   d. Run: make lint (in project_root); add to errors if non-zero exit
   e. Run: make typecheck (in project_root); add to errors if non-zero exit
   f. Run: make test (in project_root); add to errors if non-zero exit
   g. Check diff for Dockerfile or .github/workflows changes → add to warnings
   
   Set passed = True only if errors is empty.
   
4. All subprocess calls: timeout=60, capture stdout+stderr.
5. If make targets do not exist (subprocess returns error about "No rule for target"), skip that check and add a warning.

Do NOT modify any other file.
Do NOT import from apps/, libs/, or freqtrade/.
```

---

### Stage 10: Phase review

**Objective:** Wire the `--phase-review` command to run a phase exit review using `cloud_high` and post the result to Discord with an approval gate.

**Files touched:** `agent-orchestrator/orchestrator.py`, `agent-orchestrator/prompts/phase_review.md`, `agent-orchestrator/decision_gate.py`

**Model tier:** `cloud_high`

**Acceptance criteria:**
- `python orchestrator.py --phase-review` triggers the review, posts to Discord, and waits for `!approve` or `!reject`.
- The phase review prompt is the canonical verbatim template (your battle-tested phase completion review prompt). The orchestrator prepends the context pack and sends the combined text to `cloud_high`.
- A decision record is written to `state.sqlite` and `context/decision_log.md`.

**Codex prompt:**
```
Implement the --phase-review command in agent-orchestrator/orchestrator.py, the phase_review.md prompt, and decision_gate.py.

orchestrator.py --phase-review:
1. Read current phase from state.sqlite / PHASE_TASK_MAP.md
2. Build context pack (context_builder.build_context for the last task in the phase)
3. Load prompts/phase_review.md template
4. Call prompt_runner.run_model_prompt with tier CLOUD_HIGH
   (the context pack is injected via {task_context} placeholder, prepended before the review instructions)
5. Post result to Discord using discord_notifier.format_approval_request("Phase transition", "phase-N-exit", result, timeout_minutes=60)
6. Call decision_gate.wait_for_approval("phase-N-exit") — block until approved, rejected, or timeout
7. Log decision to context/decision_log.md and state.sqlite approvals table
8. Print outcome and exit

prompts/phase_review.md:
Write the following content VERBATIM — do not paraphrase or restructure:

---
{task_context}

Read these files first and treat them as authoritative:
* AGENTS.md
* docs/ARCHITECTURE.md
* docs/IMPLEMENTATION_PLAN.md
* docs/TASK_QUEUE.md
* docs/PHASE_TASK_MAP.md
* docs/MANUAL_WIRING_CHECKLIST.md

We have completed the tasks mapped to the current phase.
Your job is not to implement the next task yet.
Your job is to perform a phase completion review and keep the project aligned to its intended goal:
* staged autonomous crypto trading system
* paper-trading first
* periodic operator updates through bot/chat/reporting
* future live execution only after explicit promotion and later manual wiring
* deterministic risk governor remains authoritative over hard constraints

For the current phase:
1. identify which phase is under review
2. list the tasks mapped to that phase
3. assess whether the phase deliverables from IMPLEMENTATION_PLAN.md are actually satisfied
4. assess whether the required tests for that phase exist and are sufficient
5. assess whether the acceptance criteria are truly met
6. determine whether any manual wiring is now required for honest validation:
   * none required
   * optional
   * required now
7. if manual wiring is required, list exactly:
   * what must be wired
   * why it is required now
   * what can still remain mocked
   * what should not be wired yet
8. identify any gaps, drift, or incomplete work that must be finished before the phase is considered complete
9. recommend one of:
   * phase complete, proceed
   * phase complete but do manual wiring first
   * phase not complete, finish these remaining items first

Constraints:
* do not start coding
* do not skip milestone review
* do not recommend live wiring early unless it is genuinely required
* prefer mock-mode validation unless real integration is necessary to validate the phase honestly
* keep the review concrete and tied to the docs

Return:
1. phase under review
2. completion assessment
3. manual wiring assessment
4. remaining gaps, if any
5. recommended next action
---

Do NOT alter the prompt text in phase_review.md — it must be preserved exactly as specified above.

decision_gate.py:
1. Define wait_for_approval(ref: str, db_path: str, timeout_seconds: int) -> bool
   - Poll state.sqlite approvals table every 10 seconds for a row matching ref with decision set
   - Return True if approved, False if rejected or timeout
2. Define record_decision(ref: str, gate_type: str, decision: str, notes: str, db_path: str) -> None
   - INSERT into approvals table
   - Also append to context/decision_log.md

Do NOT modify any other file.
```

---

### Stage 11: Approval gates

**Objective:** Wire approval gates into `prompt_runner.py` and `orchestrator.py --run-next` for risky tasks.

**Files touched:** `agent-orchestrator/orchestrator.py`, `agent-orchestrator/prompt_runner.py`

**Model tier:** `cloud_high` for risk review; `local_medium` for standard tasks

**Acceptance criteria:**
- `orchestrator.py --run-next` checks the task's affected files against `FORBIDDEN_PATHS` and `RISKY_TASK_TYPES`.
- Risky tasks trigger a `risk_review.md` prompt before generating the Codex prompt, requiring human approval.
- Non-risky tasks proceed directly to Codex prompt generation.

**Codex prompt:**
```
Implement approval gate logic in agent-orchestrator/orchestrator.py --run-next command and prompts/risk_review.md.

orchestrator.py --run-next:
1. Read next pending task from state.sqlite / TASK_QUEUE.md
2. Check task's "Files likely affected" field against FORBIDDEN_PATHS
3. Check if task type requires risky gate (touching libs/risk/, apps/supervisor/, freqtrade/)
4. If risky:
   a. Build context, call risk_review.md prompt with CLOUD_HIGH tier
   b. Post approval request to Discord
   c. Wait for approval (decision_gate.wait_for_approval)
   d. If rejected: log and exit
5. If not risky:
   a. Build context, call prompt_runner.assemble_prompt with run_next_task.md (no model call)
6. Write output to agent-orchestrator/last_prompt.md
7. Post status update to Discord
8. Log activity

prompts/risk_review.md:
Template that presents the task description and affected files, then asks:
"Does this task touch risk controls, supervisor logic, live trading config, or exchange credentials?
List any concerns. Should a human review this before a Codex prompt is generated? Answer YES or NO with brief reasoning."

Do NOT modify any other file.
```

---

### Stage 12: Optional automation (Mode B scaffold)

**Objective:** Add a `--auto` flag scaffold that would invoke Codex CLI, gated behind a config flag and human approval. Do not enable by default.

**Files touched:** `agent-orchestrator/orchestrator.py`, `agent-orchestrator/config.example.yaml`

**Model tier:** None (CLI invocation)

**Acceptance criteria:**
- `codex_mode: manual` is the default in `config.example.yaml`. With `manual`, `--auto` flag prints a warning and exits.
- With `codex_mode: auto`, `--auto` invokes `codex run --prompt-file agent-orchestrator/last_prompt.md` only after a human approval gate is satisfied.
- The `--dry-run` flag passes `--dry-run` to Codex CLI and skips actual file modification.

**Codex prompt:**
```
Add Mode B scaffold to agent-orchestrator/orchestrator.py.

Requirements:
1. Add codex_mode to config loading (read from config.yaml: codex_mode: "manual" | "auto"; default "manual")
2. Add --auto CLI flag to orchestrator.py
3. If --auto and codex_mode == "manual":
   Print: "Auto mode is disabled. Set codex_mode: auto in config to enable. Exiting."
   Exit 1
4. If --auto and codex_mode == "auto":
   a. Confirm last_prompt.md exists (error if not)
   b. Require human approval gate: post Discord message "About to invoke Codex CLI on last_prompt.md. Reply !approve auto-run to proceed."
   c. Wait for approval (decision_gate.wait_for_approval)
   d. If approved: subprocess.run(["codex", "run", "--prompt-file", "agent-orchestrator/last_prompt.md"])
   e. Run validator.validate() after Codex completes
   f. Log activity
5. Add --dry-run flag: if set, append --dry-run to codex subprocess args

Do NOT enable auto mode by default.
Do NOT modify any other file.
```

---

## 13. Codex Handoff Packet

For each stage, a summary of what to hand to Codex:

| Stage | Codex inspects | Codex may create/modify | Off-limits | Expected output |
|---|---|---|---|---|
| 1 | This plan document | `agent-orchestrator/` (all new files) | Everything outside `agent-orchestrator/` | Directory with stub files |
| 2 | `agent-orchestrator/local_llm_client.py` | `agent-orchestrator/local_llm_client.py` | All other files | Working LM Studio client |
| 3 | `agent-orchestrator/model_router.py` | `agent-orchestrator/model_router.py` | All other files | ModelTier enum + route() |
| 4 | `agent-orchestrator/context_builder.py`, `task_queue_reader.py`, `docs/TASK_QUEUE.md` | Both context files | Everything outside `agent-orchestrator/` | Context assembly functions |
| 5 | `agent-orchestrator/orchestrator.py`, `docs/PHASE_TASK_MAP.md` | `agent-orchestrator/orchestrator.py`, `agent-orchestrator/state.sqlite` (init) | All project files | `--status` command working |
| 6 | `agent-orchestrator/discord_notifier.py` | `agent-orchestrator/discord_notifier.py` | All other files | Webhook + mock notifier |
| 7 | `agent-orchestrator/activity_logger.py` | `agent-orchestrator/activity_logger.py` | All other files | `ACTIVITY.md` append + sqlite insert |
| 8 | `agent-orchestrator/prompt_runner.py`, `agent-orchestrator/prompts/` | Both files | All project files | `assemble_prompt` (no model) + `run_model_prompt` + verbatim `run_next_task.md` and `phase_review.md` templates |
| 9 | `agent-orchestrator/validator.py` | `agent-orchestrator/validator.py` | All other files | Validation suite |
| 10 | `orchestrator.py`, `decision_gate.py`, `prompts/phase_review.md` | All three files | All project files | Phase review command |
| 11 | `orchestrator.py`, `prompt_runner.py`, `prompts/risk_review.md` | All three | All project files | Approval gate logic |
| 12 | `orchestrator.py`, `config.example.yaml` | Both | All project files | Mode B scaffold (disabled) |

---

## 14. External Setup Checklist

- [ ] **Python environment:** Python 3.11+ installed. Create venv: `cd agent-orchestrator && python -m venv .venv && source .venv/bin/activate`
- [ ] **Dependencies:** `pip install requests openai python-dotenv pyyaml`
- [ ] **`.env` file:** Copy `agent-orchestrator/.env.example` to `agent-orchestrator/.env`; fill in values.
- [ ] **LM Studio:** Download from lmstudio.ai. Download a 7B Q4 model. Start the local server on port 1234. Confirm `http://localhost:1234/v1/models` returns 200.
- [ ] **Discord webhook:** Create webhook in your server's `#dev-orchestrator` channel. Add URL to `.env` as `DISCORD_WEBHOOK_URL`. Test: `python -c "from discord_notifier import notify; notify('test', '<your-url>')"`.
- [ ] **Cloud API key:** Add `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`) to `.env`. Only needed when local model unavailable or task tier is `cloud_high`+.
- [ ] **Codex (optional, Mode B):** Install Codex CLI per Anthropic/OpenAI documentation. Authenticate. Set `codex_mode: auto` in `config.yaml` only when ready.
- [ ] **Safe defaults confirmed:** `codex_mode: manual`, no live config paths in context, no `.env` from repo root imported.
- [ ] **Context files populated:** Write initial content for `agent-orchestrator/context/project_summary.md`, `current_phase.md`, and `architecture_rules.md` before first run.

---

## 15. Reusability Plan

The orchestrator becomes a reusable framework by making the following components project-agnostic:

**Already generic (no changes needed):**
- `model_router.py` — task types are strings; any project can define its own.
- `local_llm_client.py` / `cloud_llm_client.py` — pure API clients.
- `discord_notifier.py` — message format is configurable.
- `activity_logger.py` — schema is generic.
- `validator.py` — `make` targets and forbidden paths are configurable.
- `decision_gate.py` — gate types are strings.

**Parameterize per project:**
- `context/project_summary.md` — replace with any project's summary.
- `context/architecture_rules.md` — replace with any project's constraints.
- `task_queue_reader.py` — the markdown format is simple and can be adapted; or swap for a JSON/YAML task queue with minimal code change.
- `config.example.yaml` — add project-specific keys.
- `prompts/` — all templates are plain text; swap for any project domain.

**To extract into a standalone package (future):**
1. Move `agent-orchestrator/` to its own repo.
2. Make `project_root`, `task_queue_path`, `context_dir`, and `prompts_dir` all configurable via `config.yaml`.
3. Publish as a pip-installable package with a `orchestrator init` command that scaffolds the context and prompt templates for a new project.
4. The trading bot repo then adds it as a dev dependency: `pip install dev-orchestrator`.

---

## 16. Resume Framing

**Agent Orchestration System — Crypto Bot Development Infrastructure**

*Designed and implemented a hybrid local/cloud LLM orchestration layer for managing the development lifecycle of a production-grade algorithmic trading system.*

Key engineering contributions:
- **Hybrid model routing:** Designed a tiered model selection system routing routine tasks to locally hosted LLMs (LM Studio, 7B–13B parameter models) and escalating to cloud APIs (GPT-4o, Claude) only for architectural reviews, failure diagnosis, and phase gates — cutting inference costs by an estimated 70–80% compared to cloud-only approaches.
- **Agentic development workflow:** Built a stateful development orchestrator that reads structured task queues, assembles minimal context packs, generates Codex-ready implementation prompts, runs post-implementation validation, and maintains an append-only audit log — enabling reproducible, trackable feature delivery.
- **Human-in-the-loop safety:** Implemented a Discord-integrated approval gate system that blocks progress on risky file changes, phase transitions, architecture modifications, and automated Codex invocations until explicit human approval is received — preventing uncontrolled autonomous mutation of production-critical components.
- **Context efficiency engineering:** Developed a token-budget-aware context builder that assembles phase-specific, task-specific, and diff-aware context packs within a 4,096-token ceiling — enabling local 7B models to produce high-quality outputs without exceeding context windows.
- **Reusable framework design:** Architected the orchestrator as a project-agnostic tool with swappable context, prompt templates, and task queue formats — suitable for extraction into a standalone dev-ops agent framework applicable to any software project.

*Technologies: Python, SQLite, LM Studio, OpenAI API, Anthropic API, Discord Webhooks, subprocess, Git.*
