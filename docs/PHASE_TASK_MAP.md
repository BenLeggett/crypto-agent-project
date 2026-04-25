# Phase Task Map

Canonical file: `docs/PHASE_TASK_MAP.md`

## Purpose

This file maps `docs/IMPLEMENTATION_PLAN.md` phases to the exact task numbers in `docs/TASK_QUEUE.md`.

It does not rewrite the project, change goals, reorder tasks, or broaden scope. The implementation plan and task queue remain the source of truth.

## Manual wiring labels

- `not expected`: phase can be validated with local config, fixtures, mocks, or placeholder interfaces.
- `optional`: real external wiring may improve validation, but mocks/local validation are acceptable for phase exit.
- `required for honest validation`: phase cannot be honestly considered complete in a real operating environment without human-owned setup, credentials, endpoints, sign-off, or external integration checks.

---

## Phase 1 - Repo skeleton and config foundation

### Primary tasks
- 1. Create repo skeleton
- 2. Add config models and loader
- 3. Add config validation tests
- 4. Add shared logging setup
- 41. Add manual wiring checklist and secret-boundary scaffolding

### Partial cross-phase support
- Task 41 also supports later secret-backed phases by documenting env placeholders, mock-safe defaults, and manual follow-up steps.
- Task 2 supports all later phases through shared config loading and validation.

### Manual wiring
- not expected

### Phase exit checklist
- Repo structure, placeholder packages, app entrypoints, config files, logging defaults, `.env.example`, and manual wiring checklist are present.
- Config schema, environment override, and app startup smoke tests are present and passing.
- Acceptance criteria reviewed: apps boot with valid config, invalid config fails fast, and dry-run/live config differences are controlled.
- Manual wiring is not required; only placeholders and checklist entries are required.

---

## Phase 2 - Market data ingestion and storage

### Primary tasks
- 5. Implement CCXT client wrapper
- 6. Build OHLCV collector job
- 7. Implement storage layer for Parquet and DuckDB
- 8. Add market-data quality checks
- 9. Add market-data tests

### Partial cross-phase support
- Tasks 5-9 provide the market-data foundation for Phases 3, 4, 5, and 8.

### Manual wiring
- not expected

### Phase exit checklist
- CCXT read wrapper, collector jobs, normalization, quality checks, Parquet storage, and DuckDB registration are present.
- Mocked collector, storage round-trip, and data quality tests are present and passing.
- Acceptance criteria reviewed: bootstrap works for configured symbols/timeframes, incremental updates are idempotent, and corrupt data is blocked.
- Manual wiring is not required; public/mock market-data validation is sufficient.

---

## Phase 3 - Deterministic strategy library

### Primary tasks
- 10. Define strategy interfaces
- 11. Implement universe selection module
- 12. Implement regime filter module
- 13. Implement breakout signal module
- 14. Implement sizing and stop modules
- 15. Implement signal snapshot schema and builder
- 16. Add strategy unit tests

### Partial cross-phase support
- Tasks 10-16 support Phases 4, 5, 8, 12, and 13 by creating the shared deterministic strategy core.

### Manual wiring
- not expected

### Phase exit checklist
- Shared strategy interfaces, universe selection, regime filter, breakout logic, sizing, stops, and signal snapshots are present.
- Strategy unit tests and snapshot determinism tests are present and passing.
- Acceptance criteria reviewed: strategy functions are pure, deterministic, repeatable, and have no exchange/network dependency.
- Manual wiring is not required.

---

## Phase 4 - Research harness and walk-forward evaluation

### Primary tasks
- 17. Add research helpers and backtest utilities
- 18. Implement walk-forward runner
- 19. Add research tests

### Partial cross-phase support
- Tasks 17-19 support later promotion decisions in Phases 8, 12, and 13.

### Manual wiring
- not expected

### Phase exit checklist
- Research entrypoint, reusable helpers, reports, and walk-forward runner are present.
- Research helper, split integrity, and metric regression tests are present and passing.
- Acceptance criteria reviewed: walk-forward outputs are versioned, metrics are reproducible, and promotion decisions can reference saved artifacts.
- Manual wiring is not required.

---

## Phase 5 - Freqtrade integration

### Primary tasks
- 20. Implement Freqtrade strategy adapter
- 21. Add Freqtrade configs and wrappers
- 22. Add Freqtrade integration tests

### Partial cross-phase support
- Task 21 partially supports Phases 12 and 13 because live config exists as a gated future path.
- Task 20 supports Phases 8 and 13 by keeping research, dry-run, and future live execution on shared strategy logic.

### Manual wiring
- not expected

### Phase exit checklist
- Freqtrade adapter imports shared strategy logic instead of duplicating it.
- Dry-run and live config templates and command wrappers are present.
- Adapter integration, backtest smoke, and parity tests are present and passing.
- Acceptance criteria reviewed: dry-run boots with configured symbols, shared logic is reused, and backtest/live paths use the same core rule set.
- Manual wiring is not required; live credentials must not be wired during this phase.

---

## Phase 6 - Supervisor and risk controls

### Primary tasks
- 23. Implement risk policy module
- 24. Implement supervisor service
- 25. Implement freeze and kill-switch controls
- 26. Implement reconciliation flow
- 27. Add supervisor tests

### Partial cross-phase support
- Tasks 25 and 26 partially support Phases 8, 12, and 13 by providing freeze, flatten, and reconciliation behavior.
- Task 27 partially supports Phase 12 by proving failure-path behavior before live readiness.

### Manual wiring
- optional

### Phase exit checklist
- Risk policy, supervisor service, health checks, freeze, flatten, kill-switch, reconciliation, and alert hooks are present.
- Risk rule, freeze/flatten, reconciliation, and degraded-health tests are present and passing.
- Acceptance criteria reviewed: supervisor can veto entries, freeze entries, trigger flatten workflows, and detect reconciliation mismatches.
- Manual wiring is optional; real alert channels may remain mocked until later validation.

---

## Phase 7 - Journaling and event packets

### Primary tasks
- 28. Implement journal schema and writer
- 29. Implement event packet schemas and builders
- 30. Wire journal and packets into execution and supervisor
- 31. Add replay utility

### Partial cross-phase support
- Tasks 28-30 support Phases 10 and 11 by creating the journal/event-packet source material for retrieval and AI jobs.
- Task 31 supports Phases 12 and 13 by enabling incident reconstruction and audit review.

### Manual wiring
- not expected

### Phase exit checklist
- Append-only journal writer, journal schemas, event packet schemas, builders, serializers, and replay utility are present.
- Journal append, event schema, and replay determinism tests are present and passing.
- Acceptance criteria reviewed: signals, orders, fills, freezes, restarts, and mismatches emit compact, versioned, machine-readable records.
- Manual wiring is not required.

---

## Phase 8 - Paper-trading end-to-end

### Primary tasks
- 32. Implement paper-mode end-to-end compose setup
- 33. Add end-to-end paper tests

### Partial cross-phase support
- Tasks 30 and 31 provide the journal, packet, and replay foundation required for reviewable paper mode.
- Task 38 later extends the reporting path with nightly rollups and daily briefing jobs.
- Task 40 later hardens promotion checklist and safety drill coverage.

### Manual wiring
- optional

### Phase exit checklist
- Collector, Freqtrade dry-run, supervisor, journaling, and paper-mode compose setup run together.
- End-to-end paper tests for restart recovery, data-gap handling, and steady-state operation are present and passing.
- Acceptance criteria reviewed: system runs continuously in paper mode, restarts do not corrupt state, and paper output is reviewable from journals/reports.
- Manual wiring is optional; external notifications may remain mocked unless validating real operator delivery.

---

## Phase 9 - AI router and cost controls

### Primary tasks
- 34. Implement AI router core
- 35. Add AI budget and usage ledger
- 36. Add prompt registry and versioning

### Partial cross-phase support
- Tasks 34-36 support Phases 10 and 11 by enforcing the only approved model-call boundary.
- Task 41 supports this phase through provider env placeholders, mocks, and manual setup notes.

### Manual wiring
- not expected

### Phase exit checklist
- AI router, provider abstraction, schemas, budgets, usage ledger, and prompt registry are present.
- Router policy, budget enforcement, schema validation, and provider mock tests are present and passing.
- Acceptance criteria reviewed: no model call exists outside `apps/ai_router`, over-budget calls fail closed, and successful outputs are schema-validated/logged.
- Manual wiring is not required; mock providers are sufficient for phase exit.

---

## Phase 10 - Retrieval and cheap advisory jobs

### Primary tasks
- 37. Implement retrieval layer with SQLite FTS5
- 38. Build nightly rollups and daily briefing jobs

### Partial cross-phase support
- Tasks 28-31 provide journal, packet, and replay inputs for retrieval and rollups.
- Tasks 34-36 provide the AI router, budget, and prompt infrastructure required by briefing jobs.
- Task 38 partially supports Phase 8 reporting and Phase 13 review cadence.

### Manual wiring
- required for honest validation

### Phase exit checklist
- SQLite FTS5 retrieval, corpus builder, nightly rollups, daily briefing job, and daily report emission path are present.
- Retrieval relevance, corpus update, and rollup job tests are present and passing.
- Acceptance criteria reviewed: daily briefing uses compact summaries/retrieval instead of raw log dumps, retrieval updates incrementally, and AI outputs remain bounded by router policy.
- Manual wiring is required only to validate real bot/chat/operator delivery; generation can still be tested with mocks/local output before credentials exist.

---

## Phase 11 - Premium offline escalation lane

### Primary tasks
- 39. Build weekly premium review and experiment-card jobs

### Partial cross-phase support
- Tasks 34-38 provide the router, budgets, prompts, retrieval, rollups, and advisory artifacts this phase depends on.
- Task 39 supports Phases 12 and 13 by producing controlled offline review artifacts.

### Manual wiring
- optional

### Phase exit checklist
- Weekly review job, experiment-card generation, escalation rules, and premium approval logging are present.
- Escalation rule, premium quota, and output schema tests are present and passing.
- Acceptance criteria reviewed: premium model usage is offline only, attributed to job/reason/budget records, and not required for paper/live operation.
- Manual wiring is optional; real premium provider credentials may remain unwired if mock-provider tests pass.

---

## Phase 12 - Live readiness gate

### Primary tasks
- 40. Add outage and safety drill tests

### Partial cross-phase support
- Task 21 supports live config templates.
- Tasks 25 and 26 support freeze, flatten, and reconciliation drills.
- Task 31 supports incident replay and audit review.
- Tasks 38 and 39 support operator reporting and offline review.
- Task 41 supports secret-boundary documentation and manual wiring notes.

### Manual wiring
- required for honest validation

### Phase exit checklist
- Promotion checklist, live caps, runbook, incident response docs, and safety drill coverage are present.
- Kill-switch, exchange disconnect, AI router outage, and config rollback tests/drills are present and passing.
- Acceptance criteria reviewed: trading remains functional when AI services are disabled, risk caps/freeze behavior are validated, and human sign-off is recorded.
- Manual wiring is required for honest readiness validation, including human review/sign-off and any real alert or environment-specific checks.

---

## Phase 13 - Small-capital live deployment

### Primary tasks
- No dedicated task currently maps exclusively to this phase.

### Partial cross-phase support
- Task 21 provides live config templates.
- Tasks 25 and 26 provide freeze, flatten, and reconciliation controls.
- Task 32 provides deployable paper-mode compose foundations.
- Task 38 supports daily reporting cadence.
- Task 40 supports safety drills and promotion gate validation.
- Task 41 supports live credential and notifier manual wiring boundaries.

### Manual wiring
- required for honest validation

### Phase exit checklist
- Dedicated live deployment work must not begin until prior phases pass and an explicit live-deployment task is added or approved.
- Production/VPS deployment, live monitoring, heartbeat, alert delivery, and post-deploy reconciliation evidence are present.
- Deployment smoke, post-deploy reconciliation, and alert delivery tests/checks are present and passing.
- Acceptance criteria reviewed: live deployment uses the paper-proven deterministic core, position sizes/exposure remain capped, and first live sessions are auditable from journals, packets, alerts, and reports.
- Manual wiring is required for live exchange credentials, real notifier endpoints, deployment environment setup, capped allocation, and human sign-off.

---

## Cross-phase notes

### Cross-cutting task
- Task 41 is primary to Phase 1 but supports every later phase that depends on secrets, credentials, webhook URLs, notifier channels, model providers, exchange accounts, wallet access, or deployment-specific environment values.

### Reporting overlap
- Task 38 belongs primarily to Phase 10 but partially supports Phase 8 and Phase 13 reporting expectations.

### Promotion and drill overlap
- Task 40 belongs primarily to Phase 12 but partially supports Phase 8 promotion review and Phase 13 live-readiness evidence.

### Live deployment coverage gap
- Phase 13 exists in the implementation plan, but the current task queue does not include a dedicated small-capital live deployment task.
- Do not infer live execution approval from this map.
- Do not wire live wallet execution until promotion criteria, safety checks, manual wiring, and explicit human sign-off are complete.