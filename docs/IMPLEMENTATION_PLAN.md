
---

# `IMPLEMENTATION_PLAN.md`

```md
# Implementation Plan

## Build strategy

Use Freqtrade as the selected trading foundation where it provides proven backtesting, dry-run/paper execution, exchange order lifecycle, and later gated live execution behavior. Custom engineering should focus on project-specific layers: deterministic risk governance, promotion gates, reporting, orchestration, audit/journaling, autonomous or model-informed analysis, and live-readiness controls.

The business objective is profitable trading, but profitability is an optimization target constrained by risk limits, evaluation evidence, observability, and staged promotion gates. The plan must not treat profitability as guaranteed or treat backtest results alone as live approval.

## Phase 1 - Repo skeleton and config foundation

### Deliverables
- Repo structure created.
- Shared config loader and validators.
- Base, dry-run, and live config sets.
- Mode flags for offline, paper, and future live operation.
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
- Live mode is not the default.
- Secret-dependent integrations expose env-var placeholders and documented manual wiring steps instead of blocking scaffolding.

## Phase 2 - Market data ingestion and storage

### Deliverables
- Freqtrade data-download/backtest-data path evaluated and wired as the default market-data foundation where practical.
- Narrow CCXT collector for OHLCV and metadata only where project-specific datasets are not covered by the foundation.
- Normalization and quality checks for project-owned datasets.
- Parquet and DuckDB storage wiring for replay, reporting, and research artifacts.
- Bootstrap and incremental update scripts that prefer framework facilities before custom collection.

### Required tests
- Collector unit tests with mocked CCXT responses.
- Storage round-trip tests.
- Data quality tests for duplicates, missing candles, timestamp ordering.

### Acceptance criteria
- Historical data bootstrap completes for configured symbols and timeframes using the selected foundation where possible.
- Incremental updates are idempotent.
- Quality checks block corrupt datasets.
- Custom collectors do not duplicate framework exchange support without a project-specific reason.

## Phase 3 - Deterministic strategy library

### Deliverables
- Shared deterministic strategy interfaces.
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
- Deterministic strategy outputs can be consumed by research, paper, and future live modes.

## Phase 4 - Research harness and walk-forward evaluation

### Deliverables
- Research entrypoint.
- Freqtrade backtesting integration used as the primary baseline where suitable.
- Walk-forward runner.
- Result storage and summary reports.
- Baseline evaluation format for deterministic and model-informed decision variants.

### Required tests
- Research helper tests.
- Walk-forward split integrity tests.
- Regression tests for metric calculations.

### Acceptance criteria
- Walk-forward runs produce versioned result artifacts.
- Metrics are reproducible.
- Strategy and decision-engine promotion decisions can be grounded in saved outputs.
- Custom research utilities add promotion/evaluation evidence instead of replacing framework backtesting wholesale.

## Phase 5 - Decision engine and autonomous proposal schema

### Deliverables
- Canonical decision input schema.
- Trade proposal/no-trade schema.
- Deterministic proposal builder from existing strategy outputs.
- Proposal validators for symbol eligibility, stale data, timestamps, sizing bounds, and required rationale fields.
- Journal records for proposal inputs and outputs.

### Required tests
- Proposal schema tests.
- Validator failure-path tests.
- Deterministic proposal fixture tests.
- Replay tests for proposal records.

### Acceptance criteria
- Decision engine emits structured proposals or no-trade decisions.
- Invalid, stale, or out-of-universe proposals fail closed.
- No proposal can place an order directly.
- Proposal records are replayable from saved inputs.

## Phase 6 - Freqtrade integration

### Deliverables
- Freqtrade installed/configured as the selected execution and research shell.
- Freqtrade strategy adapter using shared deterministic strategy/decisioning logic.
- Dry-run and live Freqtrade configs.
- Backtest and dry-run command wrappers.
- Optional wiring notes for Freqtrade-native Telegram/Web UI controls, kept mock/manual until credentials exist.

### Required tests
- Integration tests between Freqtrade adapter and strategy/decisioning library.
- Backtest smoke tests.
- Snapshot parity tests between research and Freqtrade indicator outputs where applicable.

### Acceptance criteria
- Freqtrade dry-run starts with configured symbols.
- Shared logic is imported, not duplicated.
- Backtest path and execution path use the same core rule/proposal format.
- Live config exists but is not default and cannot run without required gates and secrets.
- Custom code does not reimplement Freqtrade order lifecycle, exchange adapters, or basic runtime monitoring.

## Phase 7 - Supervisor and deterministic risk controls

### Deliverables
- Account policy engine.
- Drawdown and exposure rules.
- Allowed-market/universe enforcement.
- Max position-size rules.
- Freeze state, flatten-all, reconciliation, kill switch, health checks.
- Alert hooks.

### Required tests
- Unit tests for each risk rule.
- Integration tests for freeze and flatten flows.
- Reconciliation mismatch tests.
- Failure-path tests for health degradation.

### Acceptance criteria
- Supervisor can veto new entries from any signal source.
- Supervisor can freeze entries and flatten positions by command or policy.
- Reconciliation mismatches are detected and logged.
- Risk governor behavior is deterministic and test-backed.
- Phase 7 logging means structured JSON-compatible records and mock-safe alert
  delivery results; durable append-only journals, event packets, and replay are
  Phase 8 deliverables.

## Phase 8 - Journaling and event packets

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
- Every market snapshot, proposal, risk decision, order, fill, freeze, restart, and mismatch emits a journal record or packet.
- Packets are compact, versioned, and machine-readable.
- Replay tool can reconstruct incident and decision timelines.

## Phase 9 - Paper-trading end-to-end

### Deliverables
- Selected foundation data/execution path + decision engine + Freqtrade dry-run + supervisor + journal working together.
- Daily report script.
- Promotion checklist draft.

### Required tests
- End-to-end dry-run integration test.
- Restart recovery test.
- Data-gap handling test.
- Risk-veto path test.

### Acceptance criteria
- System runs continuously in paper mode.
- Restarts do not corrupt state.
- Paper-trading output is reviewable from journals and reports alone.
- Autonomous or model-informed proposal modes remain gated by schema validation and deterministic risk policy.

## Phase 10 - AI router and cost controls

### Deliverables
- Centralized AI router.
- Provider abstraction.
- Prompt registry and versioning.
- Budget, quota, and usage ledger.
- Structured output schemas.
- Model-informed proposal job interface.

### Required tests
- Router policy tests.
- Budget enforcement tests.
- Schema validation tests.
- Provider mock integration tests.
- Model-output failure-path tests.

### Acceptance criteria
- No model call exists outside `apps/ai_router`.
- Over-budget requests fail closed.
- All successful model outputs are schema-validated and logged.
- Model-informed proposal outputs can be tested with mocked providers.

## Phase 11 - Model-informed paper decisioning

### Deliverables
- Paper-mode model-informed analysis job.
- Prompt and schema for trade proposal/no-trade output.
- Decision-engine adapter for model-informed proposals.
- Fail-closed behavior for malformed, stale, over-budget, or unavailable model responses.
- Evaluation artifacts comparing deterministic baseline and model-informed paper results.

### Required tests
- Mocked model proposal tests.
- Invalid output rejection tests.
- AI outage behavior tests.
- Replay tests from saved model inputs and outputs.

### Acceptance criteria
- Model-informed proposals can run in paper mode only.
- Every model-informed proposal is schema-validated, journaled, and risk-checked.
- Model outage does not create uncontrolled orders.
- Paper results are measurable against saved baseline metrics.

## Phase 12 - Retrieval and operator update jobs

### Deliverables
- SQLite FTS5 retrieval index.
- Corpus builder from journals and summaries.
- Nightly rollups.
- Daily operator briefing using cheap/default model only.
- Periodic bot/chat/report update job.
- Mock notifier and manual webhook/bot wiring placeholders.
- Integration path for framework-native Telegram/Web UI status where useful, without making those credentials required.

### Required tests
- Retrieval relevance smoke tests.
- Corpus update tests.
- Rollup job tests.
- Operator update formatting tests.
- Mock notifier delivery tests.

### Acceptance criteria
- Daily briefing can be generated from compact summaries and retrieval, not raw log dumps.
- Periodic operator updates include mode, proposals, fills, risk state, drawdown, health, and incidents.
- Retrieval updates incrementally.
- Real bot/chat delivery remains a manual wiring point.
- Delivery failure is logged and does not corrupt trading state.

## Phase 13 - Premium offline escalation lane

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

## Phase 14 - Promotion gates and live-readiness preparation

### Deliverables
- Promotion checklist finalized.
- Paper performance/evaluation report format.
- Live caps configured.
- Wallet/exchange credential wiring documented.
- Runbook and incident response docs finalized.
- Failure drills completed.

### Required tests
- Kill-switch drill.
- Exchange disconnect drill.
- AI router outage drill.
- Config rollback test.
- Live config validation without credentials must fail closed.

### Acceptance criteria
- Live mode cannot start without explicit config, credentials, promotion marker, and human sign-off.
- Risk caps and freeze behavior are validated under drill conditions.
- Model-informed live signal consumption, if enabled later, is explicitly covered by promotion criteria.
- Human sign-off completed for live deployment.

## Phase 15 - Future small-capital live deployment

### Deliverables
- Production deployment on one always-on Linux machine or VPS.
- Restricted live credentials wired manually.
- Small sandbox allocation configured.
- Live monitoring and heartbeat.
- Daily and weekly review cadence.

### Required tests
- Deployment smoke test.
- Post-deploy reconciliation check.
- Alert delivery test.
- Read-only exchange connectivity check before write permissions.
- Small-order or simulated-live validation where supported.

### Acceptance criteria
- Live deployment uses the same risk governor proven in paper mode.
- Position sizes and exposure remain within configured caps.
- First live sessions are fully auditable from journals, packets, alerts, and reports.
- Live rollout remains interruptible through freeze, flatten, and kill-switch controls.
