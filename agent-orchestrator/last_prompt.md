Read AGENTS.md and the relevant docs first.

Task 38: Implement AI router core
Goal: Centralize all model invocation behind one policy-enforcing service.
Files likely affected: apps/ai_router/router.py, apps/ai_router/main.py, apps/ai_router/providers.py, apps/ai_router/schemas.py
Done criteria: router supports approved providers, structured outputs, and fail-closed policy checks.

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
