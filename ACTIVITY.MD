# Activity Log

## 2026-05-09
- Implemented local LLM preload and staged validation diagnosis for the agent orchestrator.
- Added Ollama `keep_alive` controls for low and medium local calls, startup preload readiness events, automatic async low diagnosis after validation failure, and explicit `Deep Diagnose` medium review.
- Updated the run-loop failure path so deterministic validation marks tasks failed and sets `paused=1` before any advisory model work can run.
- Updated README/config/docs/tests for the new operator workflow and model residency settings.

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

## 2026-04-25
- Implemented Task 10: shared deterministic strategy interfaces.
- Added immutable typed contracts for candles, market series, strategy context, regime assessments, entry and exit signals, sizing inputs, position sizes, stop plans, and canonical strategy snapshots.
- Added protocol boundaries for regime classifiers, entry/exit signal generators, stop planners, position sizers, and snapshot builders.
- Kept the strategy interface layer pure, framework-neutral, and free of exchange, AI, notifier, wallet, filesystem, or live-execution side effects.

## 2026-04-25
- Implemented Task 11: deterministic universe selection.
- Added config-driven universe selection contracts and a pure selector that preserves configured order while applying denylist, duplicate, quote-asset, metadata, activity, min-notional, and max-count filters.
- Added stable rejection reasons so later decisioning, reporting, journaling, and risk layers can explain why configured symbols were excluded.
- Kept universe selection local and side-effect free with no exchange, Freqtrade runtime, model, notifier, wallet, or secret dependency.

## 2026-04-25
- Implemented Task 12: deterministic daily regime filter.
- Added a moving-average and slope based classifier that emits the shared `RegimeAssessment` contract for bull, bear, range, and unknown regimes.
- Added stable regime metrics and metadata so later signal snapshots, decisioning, reporting, and replay paths can inspect the classification inputs.
- Kept regime logic pure and deterministic with no exchange, Freqtrade runtime, AI, notifier, wallet, filesystem, or secret dependency.

## 2026-04-25
- Implemented Task 13: deterministic breakout signal module.
- Added a 4h breakout/trend signal generator that emits shared `EntrySignal` and `ExitSignal` contracts from provided market series and regime assessments.
- Added stable breakout metrics and metadata for prior range, close position, and momentum so later snapshots, decisioning, reporting, and replay paths can inspect signal inputs.
- Kept breakout logic pure and deterministic with no order placement, exchange access, Freqtrade runtime, AI, notifier, wallet, filesystem, or secret dependency.

## 2026-04-25
- Implemented Task 14: deterministic sizing and stop modules.
- Added risk-budget and max-notional based position sizing that emits the shared `PositionSize` contract and preserves sizing intermediates for later snapshots, decisioning, reporting, and replay.
- Added bounded range-stop planning that emits the shared `StopPlan` contract for long and short entries with configured min/max stop distances, take-profit multiples, and optional trailing distance.
- Kept sizing and stop logic pure and deterministic with no order placement, exchange access, Freqtrade runtime, AI, notifier, wallet, filesystem, or secret dependency.

## 2026-04-25
- Implemented Task 15: canonical deterministic signal snapshot schema and builder.
- Added a pure snapshot builder that composes regime, entry, exit, stop, sizing input, and position-size outputs into the shared `StrategySnapshot` contract.
- Added a versioned machine-readable snapshot serializer for later journaling, replay, decisioning, reporting, and Freqtrade adapter use.
- Kept snapshot construction local and deterministic with no order placement, exchange access, Freqtrade runtime, AI, notifier, wallet, filesystem, or secret dependency.

## 2026-04-25
- Implemented Task 16: deterministic strategy unit-test fixture pass.
- Added fixed market-data fixtures for daily regime classification and 4h breakout snapshot construction.
- Added a fixture-backed test covering universe selection, regime classification, breakout entry, stop planning, position sizing, and serialized snapshot determinism.
- Updated README strategy notes so the maintainer can run and inspect the completed Phase 3 strategy test surface without secrets or live execution wiring.

## 2026-04-26
- Completed Phase 4 research harness coverage through Task 19.
- Added regression coverage proving saved Freqtrade-style backtest metrics and walk-forward manifests are reproducible from fixed local inputs.
- Preserved the research boundary: local artifacts only, no exchange credentials, no AI provider credentials, no notifier secrets, and no live wallet execution.
- Updated README research notes with the Phase 4 test command.

## 2026-04-26
- Reached the end of Phase 8 with completion of Task 35: journal/event packet replay utility.
- Confirmed `docs/PHASE_TASK_MAP.md` is authoritative for phase/task progress tracking and identified the activity log omission after Phase 4.
- Noted the hole in `ACTIVITY.MD`: subsequent project progress through Phases 5-8 was tracked in canonical docs and implementation artifacts, but the activity log itself was not appended until now.
- Added a corrective activity entry so the project log now reflects the current milestone and documents the oversight for future tracking discipline.

## 2026-04-26
- Implemented Task 36: paper-mode end-to-end compose setup.
- Added a mock-safe compose stack that starts paper audit bootstrap, decision-engine, supervisor, and Freqtrade dry-run services with live execution disabled.
- Added local paper runtime bootstrap artifacts for restart journaling and event packets under the configured `data/` paths.
- Preserved manual wiring boundaries: no exchange keys, wallet credentials, model provider keys, bot tokens, webhook URLs, or live config wiring are required for this task.

## 2026-04-26
- Implemented Task 37: end-to-end paper-mode integration tests.
- Added local CI-friendly coverage for restart recovery, data-gap blocking, deterministic risk veto replay, and steady-state dry-run guardrails.
- Kept validation mock/local only: no Docker runtime, exchange credentials, wallet credentials, AI provider keys, notifier secrets, or live execution are required.

## 2026-04-26
- Closed the remaining Phase 9 reporting and promotion-evidence gaps.
- Replaced the daily report placeholder with a local paper-mode JSON report over existing journal, event packet, and replay artifacts.
- Added a draft promotion checklist that records paper evidence requirements while explicitly stating it is not live approval.
- Added daily report tests and README usage notes while keeping all validation mock/local with no secrets or live wallet execution.

## [2026-05-01 00:34:42] Run 3442 Â· Phase 1 Â· Task 1

**Action:** Codex prompt generated
**Model:** none
**Outcome:** Prompt written to agent-orchestrator/last_prompt.md
**Validation:** Not provided
**Notes:** No approval gate required.

---

## [2026-05-03 00:05:12] Run 0512 Â· Phase 10 Â· Task 38

**Source:** Agent Orchestrator
**Action:** Codex prompt generated
**Model:** none
**Outcome:** Prompt written to agent-orchestrator/last_prompt.md
**Validation:** Not provided
**Notes:** No approval gate required.

---

## 2026-05-05
- Re-validated Phase 9: Paper-trading end-to-end, after the prior review was blocked by local Make and Docker dependency issues.
- Confirmed authoritative Phase 9 scope from `AGENTS.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/TASK_QUEUE.md`, `docs/PHASE_TASK_MAP.md`, and `docs/MANUAL_WIRING_CHECKLIST.md`.
- Verified mapped tasks remain Task 36, paper-mode compose setup, and Task 37, end-to-end paper tests, with the Phase 9 daily report and promotion checklist draft also present.
- Ran Phase 9 targeted validation: `python -m pytest tests/unit/test_paper_runtime_bootstrap.py tests/unit/test_paper_compose_config.py tests/integration/test_paper_mode_e2e.py tests/unit/test_daily_report.py` -> 12 passed.
- Ran broader validation through the project Make target: `make test` -> 202 passed, 2 skipped.
- Confirmed Docker availability and compose validity with `docker version`, `docker compose config`, and a one-shot `docker compose run --rm paper-audit-bootstrap ...` using container `/tmp` artifact paths.
- Cleaned up the compose validation network with `docker compose down` and confirmed no compose containers remained running.
- Assessed manual wiring as not required for Phase 9 completion; exchange keys, wallet credentials, AI provider keys, webhook/bot credentials, and live config wiring remain unwired and should not be enabled yet.
- Recorded recommendation: Phase 9 complete, proceed. The phase is validated as a mock/local paper-mode dry-run boundary; longer public-market Freqtrade dry-run operation remains optional operational smoke, not a Phase 9 blocker.

## 2026-05-08
- Implemented the Stage 12b Junction B manual-mode run-loop fix for the agent orchestrator.
- Updated `--run-loop` so manual mode keeps the process alive while paused, wakes after `!resume`, validates the existing `in_progress` task, and continues instead of requiring a restart.
- Added regression coverage for pending-to-paused prompt generation, resumed validation success, and resumed validation failure recovery.

## 2026-05-09
- Updated the agent orchestrator validator to treat Cygwin Make's `No rule to make target` wording as a missing optional target warning.
- Added validator regression coverage so absent `lint` and `typecheck` targets do not block Junction B validation.
- Hardened validator secret scanning so bare domain words like `token/cost estimate` and prior failure notes do not block validation.
- Added redacted, file-specific secret-assignment findings for high-confidence secret-like additions.
- Fixed the Stage 12b run loop phase-boundary handling so the current phase is persisted before task execution and phase exit review blocks later-phase tasks.

## 2026-05-09
- Added local-LLM advisory diagnostics around orchestrator validation failures without changing deterministic validator semantics.
- Added read-only `!explain` operator command with local-medium summary and deterministic SQLite/git fallback.
- Added prompt templates for validation failure diagnosis and latest-action explanations with explicit deterministic gate and no-live-trading constraints.

## 2026-05-09
- Hardened Discord `!explain` delivery so slow local LLM calls run off the Discord event loop and show a visible thinking message.
- Added dynamic Discord action buttons for status, explain, pause/resume, and pending approval decisions.
- Capped Discord responses and improved status output so failed tasks show failed validation plus the correct `!resume` recovery action.

## 2026-05-09
- Added a refreshing bot-owned Discord control panel so action buttons remain available beside webhook-only prompt messages.
- Made Discord progress text action-specific for explain, status, pause, resume, approve, and reject decisions.
- Removed git diff summaries from `!explain` context and deterministic explanation output, and split long Discord responses across multiple messages.
- Improved local LLM failure diagnostics so Ollama chat endpoint/model-name failures are visible instead of only saying unavailable.

## 2026-05-09
- Revised Discord controls so buttons exist only on the newest bot-owned message and are removed while a request is in flight.
- Changed button clicks to use Discord's native bot-is-thinking indicator, then attach action buttons only to the final response message.
- Kept webhook-only orchestrator updates discoverable by posting a fresh bot controls message after webhook messages.

## 2026-05-09
- Added retry/backoff for transient Discord webhook `429` and `5xx` delivery failures.
- Added local LLM retry/backoff and surfaced the underlying connection, timeout, status, or model error in diagnosis-unavailable messages.
- Annotated cleared Discord button messages with the action selected and what the current in-flight message is waiting on.

## 2026-05-09
- Added tier-specific local LLM timeout and token controls so routine low-model calls stay bounded while validation failure review can use longer medium-model timeouts.
- Added medium-model warmup before validation failure review and graceful fallback when warmup or review is unavailable.
- Kept medium local review scoped to validation failures, with compact context and no full diffs, secrets, live config, or automatic Codex repair.
- Added Discord in-flight handling for validation-failure medium review so controls are hidden, typed commands are ignored, and empty medium responses fall back instead of posting blank diagnoses.
- Reworked Discord operator updates around durable SQLite operator events and one evolving task run card so routine run-loop transitions stop spamming the channel.
- Updated the Discord task run card to use stable embed fields, friendlier failure text, collapsed progress, and followup acknowledgements so deferred button interactions do not leave the thinking indicator hanging.
- Corrected current project state: Task 38 is pending and its implementation prompt has not been run yet; older prompt-generated entries remain historical only.

## 2026-05-17
- Completed agent orchestrator Pre-Stage 12D scaffolding for stdin-based `codex exec` automation.
- Preserved `CODEX_MODE=manual` as the safe default while adding `.env.example` placeholders for `CODEX_MODEL`, `CODEX_TIMEOUT_SECONDS`, `MAX_AUTO_TASKS_PER_SESSION`, `CODEX_ENABLE_SEARCH`, and `CODEX_LAST_MESSAGE_PATH`.
- Updated generated `last_prompt.md` shape so it begins with a strict Codex task contract and keeps the existing standing implementation instructions after the contract.
- Added reusable prompt-contract linting for required fields and blocked vague phrases so Stage 12D can fail closed before invoking Codex.
- Updated the production plan to point Stage 12D implementation at the adjusted stdin design instead of the older prompt-file flow.

## 2026-05-17
- Implemented agent orchestrator Stage 12D main Mode B hardening.
- Updated `CODEX_MODE=auto` run-loop behavior to lint prompts, run `codex exec` through stdin, clear and inspect `codex_last_message.md`, pause on timeout, prompt block, clarification output, non-zero Codex exit, or validation failure, and count only successful Codex plus validation cycles toward `MAX_AUTO_TASKS_PER_SESSION`.
- Added optional `CODEX_MODEL` and opt-in `CODEX_ENABLE_SEARCH` command construction while keeping `CODEX_MODE=manual` as the documented default.
- Added Discord `!clarify <task_id> <details>` and `!skip-task <task_id>` commands; both keep the orchestrator paused until the operator sends `!resume`.
- Added regression coverage for auto happy path, prompt blocking, timeout, clarification marker, non-zero exit, session limit, clarification append, and task skip behavior.

## 2026-05-17
- Added `agent-orchestrator/docs/ORCHESTRATOR_USAGE_GUIDE.md` as the final Stage 12D operator artifact.
- Covered first-time nontechnical usage, technical environment setup, manual and auto run modes, Discord commands, Codex stdin smoke testing, failure recovery, validation commands, production checklist, and remaining manual wiring boundaries.
- Linked the guide from `README.md` so maintainers can find the operating manual from the project entry point.

## 2026-05-17
- Reconciled the Discord operator dashboard with Stage 12D Codex states.
- Added Codex-specific card event/status storytelling for prompt-blocked, clarification-needed, timeout, non-zero Codex exit, and session-limit states instead of showing all of them as generic paused states.
- Updated dashboard actions so clarification waits show `Clarify Task <id>` and `Skip Task <id>`, review waits show retry/skip actions, and unavailable buttons remain hidden while work is in flight.
- Added a Discord modal flow for clarification buttons while keeping typed `!clarify <task_id> <details>` support.

## 2026-05-17
- Added `agent-orchestrator/docs/MODE_B_UNATTENDED_READINESS_CHECKLIST.md` as the exact manual go/no-go checklist for leaving Mode B unattended.
- Included a markdown flow diagram, evidence log template, preconditions, Discord control-plane verification, manual-mode cycle, Codex stdin smoke test, prompt-block/clarification flow, controlled auto rehearsal, failure rehearsals, skip-task flow, phase-gate flow, service runtime rehearsal, and final go/no-go rollback criteria.
- Linked the readiness checklist from `README.md` and the orchestrator usage guide.

## 2026-05-24
- Fixed a Windows auto-mode Codex launch failure where `subprocess.run(["codex", ...])` could miss the npm PowerShell shim and surface as an unhandled `FileNotFoundError`.
- Updated Stage 12D command construction to prefer resolved Codex executables, including `codex.cmd` on Windows, while allowing `CODEX_CLI_PATH` as an explicit override.
- Added fail-closed handling for missing Codex CLI launches so the loop pauses with a Codex failure/review state instead of crashing through the Discord listener.
- Documented `CODEX_CLI_PATH` in the env example, usage guide, and Mode B readiness checklist.
- Ran orchestrator validation: `python -m pytest agent-orchestrator` -> 59 passed, 1 skipped, 2 subtests passed.
