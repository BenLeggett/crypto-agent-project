# Task Queue

## 1. Create repo skeleton
- Goal: Create the top-level repo directories and placeholder files matching the architecture.
- Files likely affected: `README.md`, `Makefile`, `pyproject.toml`, `docker-compose.yml`, `apps/**`, `libs/**`, `configs/**`, `docs/**`, `tests/**`
- Dependencies: none
- Done criteria: repo tree exists; imports resolve; placeholder packages are importable.

## 2. Add config models and loader
- Goal: Implement typed config models, loader, and layered override support.
- Files likely affected: `libs/config/models.py`, `libs/config/loader.py`, `libs/config/validators.py`, `configs/base/*.yaml`
- Dependencies: 1
- Done criteria: config loads from base plus environment-specific overrides; invalid config fails fast.

## 3. Add config validation tests
- Goal: Cover valid and invalid config scenarios.
- Files likely affected: `tests/unit/test_config_loader.py`, `tests/fixtures/configs/*`
- Dependencies: 2
- Done criteria: tests verify required fields, enum bounds, and override precedence.

## 4. Add shared logging setup
- Goal: Create consistent structured logging for all apps.
- Files likely affected: `libs/common/logging.py`, `configs/base/logging.yaml`, app entrypoints
- Dependencies: 2
- Done criteria: every app uses common logging config; logs include run ID and service name.

## 5. Implement CCXT client wrapper
- Goal: Centralize exchange reads for market data collection.
- Files likely affected: `libs/market_data/ccxt_client.py`
- Dependencies: 2
- Done criteria: wrapper exposes OHLCV and metadata fetch methods with retry and timeout handling.

## 6. Build OHLCV collector job
- Goal: Fetch and normalize OHLCV for configured symbols and timeframes.
- Files likely affected: `libs/market_data/collectors.py`, `apps/collector/jobs.py`, `scripts/bootstrap_data.py`, `scripts/update_market_data.py`
- Dependencies: 5
- Done criteria: bootstrap and incremental collection both work for configured symbols.

## 7. Implement storage layer for Parquet and DuckDB
- Goal: Persist raw and curated datasets and register analytics tables.
- Files likely affected: `libs/market_data/storage.py`
- Dependencies: 6
- Done criteria: collected data is written to Parquet and queryable via DuckDB.

## 8. Add market-data quality checks
- Goal: Detect duplicates, gaps, out-of-order rows, and malformed candles.
- Files likely affected: `libs/market_data/quality_checks.py`, `libs/market_data/normalization.py`, `scripts/validate_data.py`
- Dependencies: 7
- Done criteria: invalid datasets are rejected before promotion to curated storage.

## 9. Add market-data tests
- Goal: Validate collector, normalization, storage, and quality checks.
- Files likely affected: `tests/unit/test_market_data.py`, `tests/integration/test_collector_storage.py`
- Dependencies: 6, 7, 8
- Done criteria: mocked and integration tests pass with deterministic fixtures.

## 10. Define strategy interfaces
- Goal: Create the shared deterministic strategy contract used by research, paper, and future live execution.
- Files likely affected: `libs/strategy/interfaces.py`
- Dependencies: 2
- Done criteria: interfaces define inputs and outputs for regime, entries, exits, sizing, and snapshots.

## 11. Implement universe selection module
- Goal: Filter the configured trading universe deterministically.
- Files likely affected: `libs/strategy/universe.py`
- Dependencies: 10
- Done criteria: universe selection is config-driven and test-covered.

## 12. Implement regime filter module
- Goal: Compute the daily regime state for gating and analysis.
- Files likely affected: `libs/strategy/regime.py`
- Dependencies: 10
- Done criteria: regime logic is pure and deterministic with unit tests.

## 13. Implement breakout signal module
- Goal: Compute 4h breakout/trend entries and exits as a deterministic baseline signal source.
- Files likely affected: `libs/strategy/breakout.py`
- Dependencies: 10, 11, 12
- Done criteria: signal logic is pure and returns stable outputs for fixed inputs.

## 14. Implement sizing and stop modules
- Goal: Compute deterministic sizing and stop values.
- Files likely affected: `libs/strategy/sizing.py`, `libs/strategy/stops.py`
- Dependencies: 10
- Done criteria: sizing and stops respect config bounds and pass edge-case tests.

## 15. Implement signal snapshot schema and builder
- Goal: Persist one canonical machine-readable view of strategy inputs and decisions.
- Files likely affected: `libs/strategy/signal_snapshot.py`
- Dependencies: 11, 12, 13, 14
- Done criteria: snapshot includes symbol, timeframe, regime, signal flags, stops, sizing inputs, config hash.

## 16. Add strategy unit tests
- Goal: Cover universe, regime, breakout, sizing, stops, and snapshot determinism.
- Files likely affected: `tests/unit/test_strategy_*.py`, `tests/fixtures/market_data/*`
- Dependencies: 11, 12, 13, 14, 15
- Done criteria: strategy library passes deterministic unit tests from fixed fixtures.

## 17. Add research helpers and backtest utilities
- Goal: Create reusable offline helpers for analysis and result generation.
- Files likely affected: `apps/research/main.py`, `apps/research/reports.py`
- Dependencies: 15
- Done criteria: research commands can load data, run strategy, and emit saved metrics.

## 18. Implement walk-forward runner
- Goal: Add walk-forward evaluation over saved datasets.
- Files likely affected: `apps/research/walkforward.py`, `scripts/run_walkforward.py`
- Dependencies: 17
- Done criteria: runner saves split metadata, metrics, and artifact paths per run.

## 19. Add research tests
- Goal: Validate split logic and metric reproducibility.
- Files likely affected: `tests/unit/test_walkforward.py`, `tests/regression/test_research_metrics.py`
- Dependencies: 18
- Done criteria: fixed input data yields stable walk-forward outputs.

## 20. Define autonomous decision/proposal schemas
- Goal: Add canonical schemas for market snapshots, decision inputs, trade proposals, no-trade decisions, and proposal rejection reasons.
- Files likely affected: `libs/decisioning/schemas.py`, `apps/decision_engine/validators.py`, `tests/unit/test_decision_schemas.py`
- Dependencies: 2, 15
- Done criteria: schemas are typed, versioned, serializable, and reject malformed proposals.

## 21. Implement deterministic proposal builder
- Goal: Convert deterministic strategy snapshots into canonical trade proposals or no-trade decisions.
- Files likely affected: `apps/decision_engine/proposal_builder.py`, `libs/decisioning/deterministic_rules.py`
- Dependencies: 20
- Done criteria: deterministic proposal builder emits stable proposal records from fixed fixtures.

## 22. Add decision validation and stale-data checks
- Goal: Ensure proposals cannot proceed if stale, out-of-universe, malformed, oversized, or missing required fields.
- Files likely affected: `apps/decision_engine/validators.py`, `libs/decisioning/scoring.py`
- Dependencies: 20, 21
- Done criteria: invalid proposals fail closed with explicit reasons.

## 23. Add decision-engine tests
- Goal: Cover deterministic proposal generation, validation failures, and replay from saved inputs.
- Files likely affected: `tests/unit/test_decision_engine.py`, `tests/fixtures/decisioning/*`
- Dependencies: 21, 22
- Done criteria: decision-engine tests prove proposal outputs are stable, structured, and replayable.

## 24. Implement Freqtrade strategy adapter
- Goal: Bridge Freqtrade hooks to shared strategy and decisioning logic.
- Files likely affected: `freqtrade/user_data/strategies/regime_breakout_strategy.py`
- Dependencies: 15, 20, 21
- Done criteria: adapter imports shared logic and does not reimplement core rules.

## 25. Add Freqtrade configs and wrappers
- Goal: Wire dry-run and future live Freqtrade configs into the repo.
- Files likely affected: `freqtrade/user_data/config.dryrun.json`, `freqtrade/user_data/config.live.json`, `configs/dry_run/freqtrade.json`, `configs/live/freqtrade.json`, `Makefile`
- Dependencies: 24
- Done criteria: dry-run config boots locally; live config exists but is not default and requires explicit live-readiness settings.

## 26. Add Freqtrade integration tests
- Goal: Verify adapter compatibility and smoke-test backtest/dry-run paths.
- Files likely affected: `tests/integration/test_freqtrade_adapter.py`
- Dependencies: 24, 25
- Done criteria: integration tests show the adapter can run using shared logic and test fixtures.

## 27. Implement risk policy module
- Goal: Add account-level constraints for exposure, drawdown, allowed markets, max position size, and entry gating.
- Files likely affected: `libs/risk/account_policy.py`, `libs/risk/position_limits.py`, `libs/risk/drawdown_rules.py`
- Dependencies: 2
- Done criteria: policy exposes deterministic allow/deny decisions with reasons.

## 28. Implement supervisor service
- Goal: Build the service that evaluates health, policy, and operational controls.
- Files likely affected: `apps/supervisor/service.py`, `apps/supervisor/main.py`, `apps/supervisor/health.py`
- Dependencies: 27
- Done criteria: supervisor boots, evaluates policy state, and emits health status.

## 29. Implement freeze and kill-switch controls
- Goal: Add explicit freeze and flatten capabilities.
- Files likely affected: `apps/supervisor/kill_switch.py`, `libs/risk/freeze_state.py`, `scripts/freeze_entries.py`, `scripts/flatten_all.py`
- Dependencies: 28
- Done criteria: commands can freeze entries and trigger flatten workflow deterministically.

## 30. Implement reconciliation flow
- Goal: Compare internal state against exchange balances and positions.
- Files likely affected: `apps/supervisor/reconciliation.py`, `scripts/reconcile_positions.py`
- Dependencies: 28
- Done criteria: mismatches are detected, classified, and logged.

## 31. Add supervisor tests
- Goal: Cover policy, freeze, kill-switch, reconciliation, and degraded-health paths.
- Files likely affected: `tests/unit/test_risk_policy.py`, `tests/integration/test_supervisor.py`
- Dependencies: 29, 30
- Done criteria: supervisor behaviors are verified with failure-path coverage.

## 32. Implement journal schema and writer
- Goal: Add append-only deterministic audit records.
- Files likely affected: `libs/journal/schema.py`, `libs/journal/writer.py`
- Dependencies: 2
- Done criteria: writer appends validated records with timestamps, run IDs, and config hashes.

## 33. Implement event packet schemas and builders
- Goal: Add compact downstream events for proposals, risk decisions, fills, rejects, restarts, freezes, and mismatches.
- Files likely affected: `libs/event_packets/schemas.py`, `libs/event_packets/builders.py`, `libs/event_packets/serializers.py`
- Dependencies: 32
- Done criteria: versioned packet schemas exist and serialize cleanly.

## 34. Wire journal and packets into decisioning, execution, and supervisor
- Goal: Emit records from strategy, decision engine, Freqtrade integration points, and supervisor actions.
- Files likely affected: `apps/decision_engine/*.py`, `apps/supervisor/*.py`, `freqtrade/user_data/strategies/regime_breakout_strategy.py`, `libs/journal/*`, `libs/event_packets/*`
- Dependencies: 24, 28, 29, 30, 32, 33
- Done criteria: core events produce journal entries and event packets automatically.

## 35. Add replay utility
- Goal: Reconstruct decision and incident timelines from journal and packet streams.
- Files likely affected: `scripts/replay_event_packets.py`
- Dependencies: 34
- Done criteria: replay produces ordered decision/incident timelines for a given run ID or date range.

## 36. Implement paper-mode end-to-end compose setup
- Goal: Run collector, decision engine, Freqtrade dry-run, supervisor, and journaling together.
- Files likely affected: `docker-compose.yml`, app entrypoints, configs
- Dependencies: 25, 28, 34
- Done criteria: one command starts the paper-trading stack locally or on a VPS.

## 37. Add end-to-end paper tests
- Goal: Verify restart recovery, data-gap handling, risk vetoes, and steady-state paper operation.
- Files likely affected: `tests/integration/test_paper_mode_e2e.py`
- Dependencies: 36
- Done criteria: end-to-end scenarios pass in CI or a dedicated integration environment.

## 38. Implement AI router core
- Goal: Centralize all model invocation behind one policy-enforcing service.
- Files likely affected: `apps/ai_router/router.py`, `apps/ai_router/main.py`, `apps/ai_router/providers.py`, `apps/ai_router/schemas.py`
- Dependencies: 2
- Done criteria: router supports approved providers, structured outputs, and fail-closed policy checks.

## 39. Add AI budget and usage ledger
- Goal: Enforce quotas, modes, and cost visibility.
- Files likely affected: `apps/ai_router/budgets.py`, `apps/ai_router/usage_log.py`, `libs/ai_costs/*`, `configs/base/ai.yaml`
- Dependencies: 38
- Done criteria: each call is logged with model tier, prompt version, token/cost estimate, and job context; over-budget calls are blocked.

## 40. Add prompt registry and versioning
- Goal: Store all prompts as versioned assets with explicit schemas.
- Files likely affected: `apps/ai_router/prompts.py`, `data/prompts/*`
- Dependencies: 38
- Done criteria: prompts are addressed by name and version; no inline ad-hoc prompts in calling code.

## 41. Implement model-informed paper proposal job
- Goal: Allow approved model-informed analysis to generate paper-mode trade proposals through the AI router.
- Files likely affected: `libs/decisioning/model_signals.py`, `apps/decision_engine/service.py`, `data/prompts/paper_trade_proposal_v1.*`, `tests/unit/test_model_signals.py`
- Dependencies: 20, 22, 38, 39, 40
- Done criteria: mocked model outputs produce validated paper proposals or explicit no-trade decisions; malformed outputs fail closed.

## 42. Add model-informed decision replay fixtures
- Goal: Store representative model input/output fixtures for regression and replay tests.
- Files likely affected: `tests/fixtures/model_decisioning/*`, `tests/regression/test_model_decision_replay.py`
- Dependencies: 41
- Done criteria: saved fixtures replay to identical accepted/rejected proposal outcomes.

## 43. Implement retrieval layer with SQLite FTS5
- Goal: Support compact context from journals, summaries, incidents, and decision history.
- Files likely affected: `libs/retrieval/sqlite_fts.py`, `libs/retrieval/filters.py`, `libs/retrieval/corpus_builder.py`
- Dependencies: 32
- Done criteria: retrieval supports metadata filtering first, lexical search second, incremental corpus updates.

## 44. Build nightly rollups and daily briefing jobs
- Goal: Produce cheap summaries and operator briefings from compact records.
- Files likely affected: `apps/report_jobs/nightly_rollups.py`, `apps/report_jobs/daily_brief.py`, `scripts/emit_daily_report.py`
- Dependencies: 39, 40, 43
- Done criteria: daily briefing is generated from rollups and retrieval results using the cheap/default model tier only.

## 45. Implement periodic operator update job
- Goal: Send periodic paper-mode updates through a mock-safe bot/chat/reporting interface.
- Files likely affected: `apps/report_jobs/operator_update.py`, `libs/notifier/schemas.py`, `libs/notifier/mock_notifier.py`, `libs/notifier/chat_webhook.py`, `scripts/emit_operator_update.py`
- Dependencies: 34, 44
- Done criteria: update payload includes mode, proposals, fills, risk state, drawdown, health, and incidents; mock delivery works without secrets.

## 46. Add operator update tests
- Goal: Validate update content, formatting, schedule inputs, and delivery failure behavior.
- Files likely affected: `tests/unit/test_operator_update.py`, `tests/unit/test_notifier.py`
- Dependencies: 45
- Done criteria: notifier failures are logged and do not block or corrupt trading state.

## 47. Build weekly premium review and experiment-card jobs
- Goal: Add controlled premium offline analysis.
- Files likely affected: `apps/report_jobs/weekly_review.py`, `apps/briefing_cli/main.py`
- Dependencies: 39, 40, 43, 44
- Done criteria: premium jobs require explicit job type, approval marker, and separate quota bucket.

## 48. Add promotion checklist and evaluation gate
- Goal: Define the evidence required to promote from paper mode toward future small-capital live mode.
- Files likely affected: `docs/PROMOTION_CHECKLIST.md`, `apps/research/reports.py`, `scripts/run_walkforward.py`
- Dependencies: 18, 37, 42, 44, 45
- Done criteria: checklist covers paper results, drawdown, risk veto behavior, replayability, operator updates, config review, and human sign-off.

## 49. Add live-readiness guardrails
- Goal: Prevent accidental live execution before explicit promotion and manual wiring.
- Files likely affected: `libs/config/validators.py`, `configs/live/*.yaml`, `freqtrade/user_data/config.live.json`, `docs/RUNBOOK.md`
- Dependencies: 25, 27, 48
- Done criteria: live mode fails closed unless required promotion marker, live caps, credentials, and explicit mode flags are present.

## 50. Add outage and safety drill tests
- Goal: Prove operation survives AI outages, notifier failures, exchange disconnects, and policy failures.
- Files likely affected: `tests/integration/test_ai_router_outage.py`, `tests/integration/test_notifier_outage.py`, `tests/integration/test_kill_switch_drill.py`, `docs/INCIDENT_RESPONSE.md`
- Dependencies: 37, 41, 45, 49
- Done criteria: model/router outage cannot create uncontrolled orders; kill switch, freeze, rollback, and notification-failure drills are documented and test-backed.

## 51. Add manual wiring checklist and secret-boundary scaffolding
- Goal: Document every secret-dependent integration as a human wiring point and keep the repo runnable with mocks/placeholders.
- Files likely affected: `docs/MANUAL_WIRING_CHECKLIST.md`, `.env.example`, `libs/config/*`, provider interfaces, setup docs
- Dependencies: 2
- Done criteria: secret-dependent settings have env-var placeholders, mock-safe defaults where appropriate, and documented manual follow-up steps in the checklist.

## 52. Prepare future live wallet wiring path
- Goal: Add later-stage scaffolding for restricted exchange/wallet credentials without enabling live execution by default.
- Files likely affected: `docs/MANUAL_WIRING_CHECKLIST.md`, `.env.example`, `configs/live/*`, `docs/RUNBOOK.md`
- Dependencies: 49, 51
- Done criteria: live wallet wiring steps, permission requirements, validation checks, and rollback steps are documented; no real secrets are committed.