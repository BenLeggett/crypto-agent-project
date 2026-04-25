# Implementation Plan

## Phase 1 - Repo skeleton and config foundation

### Deliverables
- Repo structure created.
- Shared config loader and validators.
- Base, dry-run, and live config sets.
- Makefile, Docker Compose, env example, logging defaults.
- Manual wiring checklist created for secret-dependent integrations and human-owned setup steps.

### Required tests
- Config schema validation tests.
- Environment override tests.
- App startup smoke tests.

### Acceptance criteria
- `make test` passes for config and startup tests.
- All apps boot with valid config and fail fast on invalid config.
- Dry-run and live configs differ only in approved fields.
- Secret-dependent integrations expose env-var placeholders and documented manual wiring steps instead of blocking scaffolding.

## Phase 2 - Market data ingestion and storage

### Deliverables
- CCXT collector for OHLCV and metadata.
- Normalization and quality checks.
- Parquet and DuckDB storage wiring.
- Bootstrap and incremental update scripts.

### Required tests
- Collector unit tests with mocked CCXT responses.
- Storage round-trip tests.
- Data quality tests for duplicates, missing candles, timestamp ordering.

### Acceptance criteria
- Historical data bootstrap completes for configured symbols and timeframes.
- Incremental updates are idempotent.
- Quality checks block corrupt datasets.

## Phase 3 - Deterministic strategy library

### Deliverables
- Shared strategy interfaces.
- Universe, regime, breakout, sizing, stops, signal snapshot modules.
- Signal snapshot schema.

### Required tests
- Unit tests for regime classification.
- Unit tests for breakout conditions.
- Unit tests for sizing and stop calculations.
- Snapshot determinism tests.

### Acceptance criteria
- Strategy functions are pure and deterministic.
- Same input dataset produces identical signal snapshots across runs.
- No exchange or network dependency inside `libs/strategy`.

## Phase 4 - Research harness and walk-forward evaluation

### Deliverables
- Research entrypoint.
- Vectorbt-backed baseline analysis.
- Walk-forward runner.
- Result storage and summary reports.

### Required tests
- Research helper tests.
- Walk-forward split integrity tests.
- Regression tests for metric calculations.

### Acceptance criteria
- Walk-forward runs produce versioned result artifacts.
- Metrics are reproducible.
- Strategy promotion decisions can be grounded in saved outputs.

## Phase 5 - Freqtrade integration

### Deliverables
- Freqtrade strategy adapter using shared deterministic logic.
- Dry-run and live Freqtrade configs.
- Backtest and dry-run command wrappers.

### Required tests
- Integration tests between Freqtrade adapter and strategy library.
- Backtest smoke tests.
- Snapshot parity tests between research and Freqtrade indicator outputs where applicable.

### Acceptance criteria
- Freqtrade dry-run starts with configured symbols.
- Shared logic is imported, not duplicated.
- Backtest path and live path use the same core rule set.

## Phase 6 - Supervisor and risk controls

### Deliverables
- Account policy engine.
- Drawdown and exposure rules.
- Freeze state, flatten-all, reconciliation, kill switch, health checks.
- Alert hooks.

### Required tests
- Unit tests for each risk rule.
- Integration tests for freeze and flatten flows.
- Reconciliation mismatch tests.
- Failure-path tests for health degradation.

### Acceptance criteria
- Supervisor can veto new entries.
- Supervisor can freeze entries and flatten positions by command or policy.
- Reconciliation mismatches are detected and logged.

## Phase 7 - Journaling and event packets

### Deliverables
- Append-only journal writer.
- Structured journal schemas.
- Event packet schemas, builders, serializers.
- Replay utility.

### Required tests
- Journal append integrity tests.
- Event schema validation tests.
- Replay determinism tests.

### Acceptance criteria
- Every signal, order, fill, freeze, restart, and mismatch emits a journal record or packet.
- Packets are compact, versioned, and machine-readable.
- Replay tool can reconstruct incident timelines.

## Phase 8 - Paper-trading end-to-end

### Deliverables
- Collector + strategy + Freqtrade + supervisor + journal working together in dry-run.
- Daily report script.
- Promotion checklist draft.

### Required tests
- End-to-end dry-run integration test.
- Restart recovery test.
- Data-gap handling test.

### Acceptance criteria
- System runs continuously in paper mode.
- Restarts do not corrupt state.
- Paper-trading output is reviewable from journals and reports alone.

## Phase 9 - AI router and cost controls

### Deliverables
- Centralized AI router.
- Provider abstraction.
- Prompt registry and versioning.
- Budget, quota, and usage ledger.
- Structured output schemas.

### Required tests
- Router policy tests.
- Budget enforcement tests.
- Schema validation tests.
- Provider mock integration tests.

### Acceptance criteria
- No model call exists outside `apps/ai_router`.
- Over-budget requests fail closed.
- All successful model outputs are schema-validated and logged.

## Phase 10 - Retrieval and cheap advisory jobs

### Deliverables
- SQLite FTS5 retrieval index.
- Corpus builder from journals and summaries.
- Nightly rollups.
- Daily operator briefing using cheap/default model only.

### Required tests
- Retrieval relevance smoke tests.
- Corpus update tests.
- Rollup job tests.

### Acceptance criteria
- Daily briefing can be generated from compact summaries and retrieval, not raw log dumps.
- Retrieval updates incrementally.
- AI outputs remain advisory artifacts only.

## Phase 11 - Premium offline escalation lane

### Deliverables
- Explicit escalation rules.
- Weekly post-mortem job.
- Experiment card generator.
- Approval logging for premium runs.

### Required tests
- Escalation rule tests.
- Premium quota tests.
- Output schema tests.

### Acceptance criteria
- Premium model usage occurs only in approved offline flows.
- Each premium invocation is attributable to a job, reason, and budget record.
- No premium path is required for paper or live operation.

## Phase 12 - Live readiness gate

### Deliverables
- Promotion checklist finalized.
- Live caps configured.
- Runbook and incident response docs finalized.
- Failure drills completed.

### Required tests
- Kill-switch drill.
- Exchange disconnect drill.
- AI router outage drill.
- Config rollback test.

### Acceptance criteria
- Live trading remains functional when AI services are disabled.
- Risk caps and freeze behavior are validated under drill conditions.
- Human sign-off completed for live deployment.

## Phase 13 - Small-capital live deployment

### Deliverables
- Production deployment on one always-on Linux machine or VPS.
- Live monitoring and heartbeat.
- Daily and weekly review cadence.

### Required tests
- Deployment smoke test.
- Post-deploy reconciliation check.
- Alert delivery test.

### Acceptance criteria
- Live deployment uses the same deterministic core proven in paper mode.
- Position sizes and exposure remain within configured caps.
- First live sessions are fully auditable from journals, packets, alerts, and reports.
