# Activity Log

## 2026-04-22
- Regenerated the merged Codex implementation packet from the two uploaded source documents after prior exported files were no longer available in the workspace.
- Recreated these artifacts:
  - `docs/ARCHITECTURE.md`
  - `docs/IMPLEMENTATION_PLAN.md`
  - `docs/TASK_QUEUE.md`
  - `AGENTS.md`
  - `ACTIVITY.MD`
- Preserved the locked constraints in the regenerated packet:
  - deterministic execution and risk-control core
  - AI has no unchecked live order authority
  - low-cost AI design remains event-driven, escalation-based, and mostly non-LLM in live operation

## 2026-04-25
- Appended Codex secret-boundary and manual-wiring instructions to the project docs with minimal scope changes.
- Updated `AGENTS.md` to require mock-first implementation for any feature blocked on secrets or personal credentials.
- Updated `ARCHITECTURE.md`, `IMPLEMENTATION_PLAN.md`, and `TASK_QUEUE.md` only where needed to reference manual wiring and placeholder-based scaffolding.
- Created `MANUAL_WIRING_CHECKLIST.md` as the referenced log for human-owned setup steps and secret-backed integrations.

## 2026-04-25
- Performed a second-pass alignment update to reflect the actual staged autonomous crypto trading bot goal.
- Corrected docs that over-constrained the system to deterministic-only trading and AI-advisory-only behavior.
- Preserved the deterministic risk governor, audit logging, replayability, kill switches, freeze/flatten controls, and promotion gates.
- Updated the architecture and plan so autonomous/model-informed signal or proposal generation is allowed in paper mode and can only progress toward future small-capital live execution after explicit review and promotion criteria.
- Added periodic bot/chat/report operator updates as a first-class paper-mode requirement.
- Kept live wallet execution as a later anticipated phase, not an immediate default.

## 2026-04-25
- Implemented Slice 1: repo skeleton and importable foundation.
- Created the planned `apps/`, `libs/`, `configs/`, `freqtrade/`, `scripts/`, `data/`, `notebooks/`, `docs/`, and `tests/` layout.
- Added safe placeholder entrypoints that do not access exchanges, wallets, AI providers, webhooks, or production-only settings.
- Mirrored the architecture, implementation plan, task queue, and manual wiring checklist into `docs/` so the repository matches the documented canonical paths.
- Added `.env.example`, `pyproject.toml`, `Makefile`, `docker-compose.yml`, and import smoke tests.
- Preserved paper-first behavior and left live execution gated and disabled by default.

## 2026-04-25
- Added `.gitignore` tuned for the paper-first trading system.
- Excluded local secrets, Python caches, virtual environments, runtime market data, journals, summaries, Freqtrade generated state, logs, notebook checkpoints, build outputs, and editor/OS noise.
- Preserved tracked placeholders such as `.env.example` and `.gitkeep` files.

## 2026-04-25
- Implemented Task 2: typed config models and layered config loader.
- Added dataclass config models, fail-fast validators, and a dependency-free loader for the current simple YAML config files.
- Supported `configs/base/` plus `configs/dry_run` or `configs/live` app overlays, with explicit environment variable overrides.
- Preserved paper-first defaults, kept live execution disabled, and made real AI provider selection fail closed without `OPENAI_API_KEY`.
- Added config loader tests for defaults, live gating, environment overrides, invalid modes, live execution rejection, and AI provider secret boundaries.

## 2026-04-25
- Implemented Task 3: config validation tests.
- Added fixture-backed valid config files under `tests/fixtures/configs/valid`.
- Expanded config tests for required fields, enum bounds, override precedence, live promotion gating, deterministic risk governor enforcement, premium model guardrails, and AI provider secret behavior.

## 2026-04-25
- Performed a third-pass docs reconciliation to clarify the practical build strategy.
- Aligned docs around using the existing Freqtrade-leaning foundation for execution, dry-run, backtesting, and later gated live paths where appropriate.
- Clarified that custom engineering should focus on deterministic risk governance, promotion gates, audit/journaling, reporting, orchestration glue, model-informed analysis boundaries, and live-readiness controls rather than rebuilding solved framework capabilities.
- Documented profitable trading as the business optimization target while preserving risk constraints, evaluation discipline, staged promotion gates, and no guarantee of profitability.

## 2026-04-25
- Reconciled completed foundation work with the Freqtrade-first direction.
- Added an explicit `trading_foundation: freqtrade` config field and validation guardrail so the selected foundation cannot drift silently.
- Updated README messaging to reflect the profitability objective, risk-constrained promotion discipline, and custom-vs-foundation split.
- Replaced root-level duplicate planning docs with pointers to canonical files under `docs/`.

## 2026-04-25
- Implemented Task 4: shared logging setup.
- Added stdlib-only structured/plain logging configuration with `service_name` and `run_id` context.
- Wired placeholder app entrypoints through the shared logger instead of direct `print` output.
- Added logging tests for structured fields, handler replacement, plain context output, and app startup logging.

## 2026-04-25
- Implemented Task 5: narrow CCXT read client wrapper.
- Added typed OHLCV and market metadata records, retry/timeout handling, and an optional public CCXT exchange factory.
- Kept CCXT optional and mock-first so local tests require no exchange credentials, secrets, or network calls.
- Added unit tests for parsing, retries, malformed responses, constructor validation, and optional factory behavior.

## 2026-04-25
- Implemented Task 6: OHLCV collector job.
- Added Freqtrade-first `download-data` command construction and a command-runner boundary so bootstrap/update behavior can be tested without Freqtrade, network access, or credentials.
- Wired bootstrap and incremental update scripts plus Make targets while preserving paper-first defaults and no live wallet behavior.
- Added mocked unit tests for command construction, job overrides, update windows, validation failures, and command failures.

## 2026-04-25
- Implemented Task 7: market-data storage layer.
- Added typed OHLCV dataset rows, deterministic Parquet output paths, and DuckDB table registration/query interfaces.
- Kept `pyarrow` and `duckdb` as optional local dependencies and tested storage behavior through fake backends so no secrets, exchange access, or live execution wiring is required.
- Added storage unit tests for row conversion, write/register/query flow, dataset validation, and safe default table naming.

## 2026-04-25
- Implemented Task 8: market-data normalization and quality checks.
- Added deterministic OHLCV normalization plus checks for duplicate timestamps, out-of-order candles, gaps, malformed candle ranges, negative values, mixed datasets, and empty datasets.
- Wired `scripts/validate_data.py` and a `make data-validate` target for local Parquet validation when optional market-data dependencies are installed.
- Added mocked unit tests for normalization, quality failures, timeframe conversion, and validation script behavior.

## 2026-04-25
- Implemented Task 9: market-data test coverage pass.
- Added a public API unit test that exercises Freqtrade command construction, OHLCV row conversion, normalization, and quality validation together.
- Added a mocked integration test that flows CCXT OHLCV rows through validation, storage, DuckDB-style registration, query, re-normalization, and post-storage validation.
- Kept the test path fully local and mock-backed with no exchange, Freqtrade, pyarrow, DuckDB, credentials, or live execution dependency.
