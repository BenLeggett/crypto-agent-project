# Phase Task Map

Canonical file: `docs/PHASE_TASK_MAP.md`

## Purpose

This file maps `docs/IMPLEMENTATION_PLAN.md` phases to the exact task numbers in `docs/TASK_QUEUE.md` so milestone tracking is explicit.

It does not rewrite the project, change goals, reorder tasks, or broaden scope. `docs/IMPLEMENTATION_PLAN.md` and `docs/TASK_QUEUE.md` remain the source of truth.

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
- 51. Add manual wiring checklist and secret-boundary scaffolding

### Partial cross-phase support
- Task 2 supports all later phases through shared config loading, overrides, and validation.
- Task 51 supports later secret-backed phases by documenting env placeholders, mock-safe defaults, and manual follow-up steps.

### Manual wiring
- not expected

### Phase exit checklist
- Repo structure, placeholder packages, app entrypoints, base config files, logging defaults, `.env.example`, and manual wiring checklist are present.
- Config schema, environment override, and app startup smoke tests are present and passing.
- Acceptance criteria reviewed: apps boot with valid config, invalid config fails fast, dry-run/live config differences are controlled, and live mode is not the default.
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
- Tasks 5-9 provide the market-data foundation for Phases 3, 4, 5, 8, and 9.

### Manual wiring
- not expected

### Phase exit checklist
- Freqtrade-first bootstrap/update path, narrow CCXT read wrapper, collector jobs, normalization, quality checks, Parquet storage, and DuckDB registration are present.
- Mocked collector, storage round-trip, and data quality tests are present and passing.
- Acceptance criteria reviewed: bootstrap works for configured symbols/timeframes, incremental updates are idempotent, corrupt data is blocked, and custom collection does not duplicate framework exchange support without a project-specific reason.
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
- Tasks 10-16 support Phases 4, 5, 6, 9, and later model-informed comparison work by creating the shared deterministic strategy core.

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
- Tasks 17-19 support later evidence generation for Phases 9, 11, 14, and 15.
- Task 48 later extends this phase's outputs into a formal promotion checklist and evaluation gate.

### Manual wiring
- not expected

### Phase exit checklist
- Research entrypoint, Freqtrade backtesting integration wrapper, reusable helpers, reports, and walk-forward runner are present.
- Research helper, split integrity, and metric regression tests are present and passing.
- Acceptance criteria reviewed: walk-forward outputs are versioned, metrics are reproducible, and promotion decisions can reference saved artifacts.
- Manual wiring is not required.

---

## Phase 5 - Decision engine and autonomous proposal schema

### Primary tasks
- 20. Define autonomous decision/proposal schemas
- 21. Implement deterministic proposal builder
- 22. Add decision validation and stale-data checks
- 23. Add decision-engine tests

### Partial cross-phase support
- Tasks 20-23 support Phases 6, 7, 8, 9, and 11 by defining the proposal boundary that all deterministic and model-informed outputs must pass through.
- Task 22 supports later risk and live-readiness phases by enforcing stale-data, universe, sizing, and schema failure paths before any order path.

### Manual wiring
- not expected

### Phase exit checklist
- Canonical decision input schemas, trade proposal/no-trade schemas, deterministic proposal builder, validators, and proposal journal/replay fixtures are present.
- Proposal schema, validator failure-path, deterministic fixture, and replay tests are present and passing.
- Acceptance criteria reviewed: the decision engine emits structured proposals or no-trade decisions, invalid/stale/out-of-universe proposals fail closed, and no proposal can place an order directly.
- Manual wiring is not required.

---

## Phase 6 - Freqtrade integration

### Primary tasks
- 24. Implement Freqtrade strategy adapter
- 25. Add Freqtrade configs and wrappers
- 26. Add Freqtrade integration tests

### Partial cross-phase support
- Task 24 supports Phases 9 and 15 by keeping research, dry-run, and future live execution on shared strategy/decisioning logic.
- Task 25 partially supports Phases 14 and 15 because live config templates exist as a gated future path.

### Manual wiring
- not expected

### Phase exit checklist
- Freqtrade is installed/configured as the selected execution and research shell.
- Freqtrade adapter imports shared strategy/decisioning logic instead of duplicating it.
- Dry-run and live config templates plus backtest/dry-run command wrappers are present.
- Adapter integration, backtest smoke, and parity tests are present and passing.
- Acceptance criteria reviewed: dry-run boots with configured symbols, backtest and execution paths use the same core rule/proposal format, and live config is not default and cannot run without gates/secrets.
- Manual wiring is not required; live credentials must not be wired during this phase.

---

## Phase 7 - Supervisor and deterministic risk controls

### Primary tasks
- 27. Implement risk policy module
- 28. Implement supervisor service
- 29. Implement freeze and kill-switch controls
- 30. Implement reconciliation flow
- 31. Add supervisor tests

### Partial cross-phase support
- Tasks 27-31 support Phases 9, 14, and 15 by establishing the deterministic risk governor used for paper and future live modes.
- Tasks 29 and 30 partially support Phase 14 safety drills and Phase 15 live operations through freeze, flatten, and reconciliation behavior.

### Manual wiring
- optional

### Phase exit checklist
- Risk policy, supervisor service, health checks, freeze, flatten, kill switch, reconciliation, and alert hooks are present.
- Risk rule, freeze/flatten, reconciliation, and degraded-health tests are present and passing.
- Acceptance criteria reviewed: supervisor can veto entries, freeze entries, trigger flatten workflows, detect reconciliation mismatches, and emit structured JSON-compatible records for deterministic risk decisions and mock-safe alert hooks. Append-only journals and event packets are Phase 8 deliverables.
- Manual wiring is optional; real alert channels may remain mocked until later validation.

---

## Phase 8 - Journaling and event packets

### Primary tasks
- 32. Implement journal schema and writer
- 33. Implement event packet schemas and builders
- 34. Wire journal and packets into decisioning, execution, and supervisor
- 35. Add replay utility

### Partial cross-phase support
- Tasks 32-35 support Phases 9, 11, 12, 13, 14, and 15 by creating the audit, retrieval, replay, and incident-review source material.
- Task 35 supports later promotion and live-readiness review by enabling incident and decision timeline reconstruction.

### Manual wiring
- not expected

### Phase exit checklist
- Append-only journal writer, journal schemas, event packet schemas, builders, serializers, integration wiring, and replay utility are present.
- Journal append, event schema, and replay determinism tests are present and passing.
- Acceptance criteria reviewed: market snapshots, proposals, risk decisions, orders/fills, freezes, restarts, and mismatches emit compact, versioned, machine-readable records.
- Manual wiring is not required.

---

## Phase 9 - Paper-trading end-to-end

### Primary tasks
- 36. Implement paper-mode end-to-end compose setup
- 37. Add end-to-end paper tests

### Partial cross-phase support
- Tasks 24-26 provide the Freqtrade dry-run foundation required by this phase.
- Tasks 27-31 provide the supervisor/risk-governor foundation required by this phase.
- Tasks 32-35 provide the journal, packet, and replay foundation required for reviewable paper mode.
- Task 44 later extends reporting with nightly rollups and daily briefing jobs.
- Task 48 later formalizes the promotion checklist and evaluation gate.

### Manual wiring
- optional

### Phase exit checklist
- Market-data path, decision engine, Freqtrade dry-run, supervisor, journaling, and paper-mode compose setup run together.
- End-to-end paper tests for restart recovery, data-gap handling, risk vetoes, and steady-state operation are present and passing.
- Acceptance criteria reviewed: the system runs continuously in paper mode, restarts do not corrupt state, and paper output is reviewable from journals/reports alone.
- Manual wiring is optional; external notifications may remain mocked unless validating real operator delivery.

---

## Phase 10 - AI router and cost controls

### Primary tasks
- 38. Implement AI router core
- 39. Add AI budget and usage ledger
- 40. Add prompt registry and versioning

### Partial cross-phase support
- Tasks 38-40 support Phases 11, 12, and 13 by enforcing the only approved model-call boundary.
- Task 51 supports this phase through provider env placeholders, mocks, and manual setup notes.

### Manual wiring
- not expected

### Phase exit checklist
- AI router, provider abstraction, schemas, budgets, usage ledger, and prompt registry are present.
- Router policy, budget enforcement, schema validation, provider mock, and model-output failure-path tests are present and passing.
- Acceptance criteria reviewed: no model call exists outside `apps/ai_router`, over-budget calls fail closed, and successful outputs are schema-validated and logged.
- Manual wiring is not required; mock providers are sufficient for phase exit.

---

## Phase 11 - Model-informed paper decisioning

### Primary tasks
- 41. Implement model-informed paper proposal job
- 42. Add model-informed decision replay fixtures

### Partial cross-phase support
- Tasks 20-23 provide the proposal schema and validation boundary used by model-informed outputs.
- Tasks 38-40 provide the router, budget, and prompt infrastructure required for model calls.
- Tasks 41-42 support Phase 14 by producing comparable paper-mode evidence against deterministic baselines.

### Manual wiring
- optional

### Phase exit checklist
- Paper-mode model-informed proposal job, prompt/schema assets, decision-engine adapter, fail-closed model response handling, and replay fixtures are present.
- Mocked model proposal, invalid output rejection, AI outage behavior, and replay tests are present and passing.
- Acceptance criteria reviewed: model-informed proposals run in paper mode only, every output is schema-validated/journaled/risk-checked, and outage/malformed/over-budget cases fail closed.
- Manual wiring is optional; real provider credentials are not required if mocked provider tests pass.

---

## Phase 12 - Retrieval and operator update jobs

### Primary tasks
- 43. Implement retrieval layer with SQLite FTS5
- 44. Build nightly rollups and daily briefing jobs
- 45. Implement periodic operator update job
- 46. Add operator update tests

### Partial cross-phase support
- Tasks 32-35 provide journal, packet, and replay inputs for retrieval, rollups, and operator updates.
- Tasks 38-40 provide the AI router, budget, and prompt infrastructure required by briefing jobs.
- Task 44 partially supports Phase 9 reporting and Phase 15 review cadence.
- Task 45 partially supports Phase 15 monitoring and heartbeat expectations.

### Manual wiring
- optional

### Phase exit checklist
- SQLite FTS5 retrieval, corpus builder, nightly rollups, daily briefing job, periodic operator update job, mock notifier, and manual webhook/bot placeholders are present.
- Retrieval relevance, corpus update, rollup job, operator formatting, and mock notifier delivery tests are present and passing.
- Acceptance criteria reviewed: daily briefing uses compact summaries/retrieval instead of raw log dumps, periodic updates include mode/proposals/fills/risk/drawdown/health/incidents, retrieval updates incrementally, and delivery failure is logged without corrupting trading state.
- Manual wiring is optional for phase exit; real bot/chat delivery requires human-supplied webhook or bot credentials if external delivery is claimed.

---

## Phase 13 - Premium offline escalation lane

### Primary tasks
- 47. Build weekly premium review and experiment-card jobs

### Partial cross-phase support
- Tasks 38-40 provide the router, budgets, prompts, and model policy boundaries this phase depends on.
- Tasks 43-44 provide retrieval and rollup inputs for offline review artifacts.
- Task 47 supports Phase 14 by producing controlled offline review artifacts and experiment cards.

### Manual wiring
- optional

### Phase exit checklist
- Weekly review job, experiment-card generation, escalation rules, premium quota bucket, and premium approval logging are present.
- Escalation rule, premium quota, and output schema tests are present and passing.
- Acceptance criteria reviewed: premium usage occurs only in approved offline flows, every invocation is attributable to a job/reason/budget record, and no premium path is required for paper or live operation.
- Manual wiring is optional; real premium provider credentials may remain unwired if mock-provider tests pass.

---

## Phase 14 - Promotion gates and live-readiness preparation

### Primary tasks
- 48. Add promotion checklist and evaluation gate
- 49. Add live-readiness guardrails
- 50. Add outage and safety drill tests
- 52. Prepare future live wallet wiring path

### Partial cross-phase support
- Task 18 supports promotion evidence through walk-forward evaluation artifacts.
- Task 25 supports this phase through gated live Freqtrade config templates.
- Tasks 29-30 support freeze, flatten, kill-switch, and reconciliation drills.
- Task 35 supports incident replay and audit review.
- Tasks 41-42 support evaluation of model-informed paper decisioning.
- Tasks 44-46 support operator reporting and notification-failure validation.
- Task 51 supports secret-boundary documentation and manual wiring notes.

### Manual wiring
- required for honest validation

### Phase exit checklist
- Promotion checklist, paper performance/evaluation report format, live caps, live-readiness guardrails, wallet/exchange wiring documentation, runbook, incident response docs, and safety drill coverage are present.
- Kill-switch, exchange disconnect, AI router outage, notifier failure, config rollback, and live-config fail-closed tests/drills are present and passing.
- Acceptance criteria reviewed: live mode cannot start without explicit config, credentials, promotion marker, live caps, and human sign-off; risk caps and freeze behavior are validated under drill conditions.
- Manual wiring is required for honest readiness validation, including human sign-off and any real environment-specific alert/connectivity checks. Real live credentials may remain unwired until Phase 15.

---

## Phase 15 - Future small-capital live deployment

### Primary tasks
- No dedicated task currently maps exclusively to this phase.

### Partial cross-phase support
- Task 25 provides live Freqtrade config templates.
- Tasks 29-30 provide freeze, flatten, kill-switch, and reconciliation controls.
- Task 36 provides deployable paper-mode compose foundations.
- Tasks 44-46 support reporting, operator update, and notification behavior.
- Tasks 48-50 provide promotion, live-readiness, and safety-drill evidence.
- Task 52 provides future live wallet wiring documentation and guardrail scaffolding.

### Manual wiring
- required for honest validation

### Phase exit checklist
- Dedicated live deployment work must not begin until prior phases pass and an explicit live-deployment task is added or approved.
- Production/VPS deployment, restricted live credentials, capped allocation, live monitoring, heartbeat, alert delivery, and post-deploy reconciliation evidence are present.
- Deployment smoke, post-deploy reconciliation, read-only exchange connectivity, alert delivery, and small-order or simulated-live validation checks are present and passing where supported.
- Acceptance criteria reviewed: live deployment uses the paper-proven deterministic risk governor, position sizes/exposure remain capped, first live sessions are fully auditable, and rollout remains interruptible through freeze, flatten, and kill-switch controls.
- Manual wiring is required for live exchange credentials, notifier endpoints, deployment environment setup, capped allocation, and human sign-off.

---

## Cross-phase notes

### Source-of-truth rule
- This file is a tracking map only.
- If `docs/IMPLEMENTATION_PLAN.md` or `docs/TASK_QUEUE.md` changes, update this file to preserve exact task-number alignment.

### Cross-cutting task
- Task 51 is primary to Phase 1 but supports every later phase that depends on secrets, credentials, webhook URLs, notifier channels, model providers, exchange accounts, wallet access, or deployment-specific environment values.

### Model-informed decisioning boundary
- Tasks 41-42 belong primarily to Phase 11, not Phase 5, because Phase 5 establishes the canonical proposal schema and deterministic decisioning boundary first.

### Reporting overlap
- Task 44 belongs primarily to Phase 12 but partially supports Phase 9 paper-trading reporting and Phase 15 review cadence.
- Tasks 45-46 belong primarily to Phase 12 but partially support Phase 15 monitoring expectations.

### Promotion and drill overlap
- Tasks 48-50 belong primarily to Phase 14 but partially support Phase 15 live-readiness evidence.

### Live deployment coverage gap
- Phase 15 exists in the implementation plan, but the current task queue does not include a dedicated small-capital live deployment implementation task.
- Do not infer live execution approval from this map.
- Do not wire live wallet execution until promotion criteria, safety checks, manual wiring, explicit live-deployment work, and human sign-off are complete.
