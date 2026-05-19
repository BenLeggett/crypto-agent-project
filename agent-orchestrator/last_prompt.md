# Codex Task Contract

You are running in a headless automation loop.

You must not infer missing scope.

If the task objective, allowed modification files, acceptance criteria, or validation commands are unclear, stop without modifying files and print:

CODEX_NEEDS_CLARIFICATION:
<specific missing information>

Do not make a best-effort implementation when the task contract is incomplete.

TASK_ID: 38
TASK_TITLE: Implement AI router core

OBJECTIVE:
Centralize all model invocation behind one policy-enforcing service.

FILES_ALLOWED_TO_MODIFY:
- apps/ai_router/router.py
- apps/ai_router/main.py
- apps/ai_router/providers.py
- apps/ai_router/schemas.py

FILES_ALLOWED_TO_INSPECT:
- AGENTS.md
- docs/TASK_QUEUE.md
- docs/PHASE_TASK_MAP.md
- docs/IMPLEMENTATION_PLAN.md
- apps/ai_router/router.py
- apps/ai_router/main.py
- apps/ai_router/providers.py
- apps/ai_router/schemas.py

OUT_OF_SCOPE:
- Do not modify files outside FILES_ALLOWED_TO_MODIFY.
- Do not refactor unrelated code.
- Do not introduce new dependencies unless explicitly listed.
- Do not change environment files, secrets, CI, deployment, or live config.
- Do not make architectural changes unless explicitly requested.

ACCEPTANCE_CRITERIA:
- router supports approved providers, structured outputs, and fail-closed policy checks.

VALIDATION_COMMANDS:
- Run targeted tests for changed modules.
- python -m pytest

STOP_CONDITIONS:
- If the target file is unclear, stop and explain the ambiguity.
- If required context is missing, stop and explain what is missing.
- If implementation requires modifying files outside FILES_ALLOWED_TO_MODIFY, stop.
- If tests or validation commands are missing and correctness cannot be verified, stop.
- If secrets, credentials, live config, deployment, or risky paths are required, stop.

## Task Queue Context
Task 38: Implement AI router core
Goal: Centralize all model invocation behind one policy-enforcing service.
Files likely affected: apps/ai_router/router.py, apps/ai_router/main.py, apps/ai_router/providers.py, apps/ai_router/schemas.py
Done criteria: router supports approved providers, structured outputs, and fail-closed policy checks.

## Standing Instructions

Read AGENTS.md and the relevant docs first.

Implement the next dependency-ordered task only.

If any dependency task appears incomplete based on the docs, stop and report the gap
rather than proceeding.

Requirements:
* preserve the staged autonomous architecture
* preserve the deterministic risk governor as authoritative over hard constraints
* preserve paper-trading-first rollout
* do not assume live wallet execution is approved yet
* implement everything possible without secrets
* where secrets would normally be needed, add interfaces, env placeholders, mocks,
  tests, and manual wiring notes
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
