# Architecture

## System boundaries

### In scope
- Market-data ingestion for a small liquid CEX spot universe.
- Continuous market analysis in paper mode.
- Deterministic and model-informed signal/proposal generation.
- Autonomous paper-trading decisions subject to deterministic validation and risk checks.
- Execution via Freqtrade for backtest, paper, and later tightly capped live trading.
- Deterministic supervisor for account-level guardrails, reconciliation, freezes, flattening, and kill switches.
- Append-only journals, event packets, reports, bot/chat updates, and operator alerts.
- AI/model plane for structured decision support, signal/proposal generation, summarization, triage, briefings, experiment support, and incident review.
- Future live-wallet execution path after promotion criteria, review, and explicit human approval.

### Out of scope
- Unchecked AI live order authority.
- Live wallet execution on day one.
- Autonomous mutation of live risk limits, leverage, universe, or deployment settings.
- Managed vector DBs, agent frameworks, or multi-agent orchestration in v1.
- Direct news/social-to-trade execution in v1.
- Any claim or assumption of guaranteed profitability.

## Operating model

### Profitability objective
- The business objective is profitable trading over time.
- Profitability is an optimization target constrained by drawdown limits, exposure limits, evaluation evidence, replayability, and staged promotion gates.
- The system must never present profit as guaranteed or treat a profitable backtest as sufficient for live approval.

### Build strategy
- Use an existing trading framework as the execution and research foundation where it fits.
- The current implementation path is Freqtrade-first for backtesting, dry-run/paper execution, exchange order lifecycle, later gated live execution, and built-in operator surfaces where useful.
- Use CCXT through Freqtrade or narrow project adapters for market-data reads instead of rebuilding broad exchange support.
- Custom code exists to add project-specific safety, evaluation, audit, reporting, orchestration, and model-boundary layers around the foundation.
- Do not introduce a second trading framework unless the docs are explicitly revised to replace the selected foundation.

### Leveraged foundation components
- Freqtrade: execution shell for backtest, dry-run, paper-forward testing, and future tightly capped live trading.
- Freqtrade strategy/config/user-data structure: adapter surface for shared deterministic strategy and decisioning logic.
- Freqtrade Telegram/Web UI features: optional operator control surfaces after manual credential wiring.
- CCXT: exchange metadata and OHLCV reads where direct collection is required.
- SQLite, Parquet, and DuckDB: local persistence, analytics, and replayable artifacts.
- SQLite FTS5: local retrieval over journals, summaries, incidents, and notes.

### Custom system components
- Deterministic risk governor and supervisor policy.
- Promotion and live-readiness gates.
- Proposal schemas, validators, and model-informed analysis boundaries.
- Audit journals, event packets, replay tools, and evidence bundles.
- Operator reporting beyond or alongside framework-native status surfaces.
- AI router, prompt registry, quotas, usage ledger, and fail-closed model outputs.
- Orchestration scripts that wire the foundation and custom safety layers together.

### Autonomous trading core
- Collects and normalizes market data.
- Computes deterministic features and/or model-ready input snapshots.
- Generates trade signals or trade proposals through deterministic or model-informed decision modules.
- Converts approved signals into execution intents.
- Sends all intents through deterministic risk validation before paper or live execution.
- Emits journals and event packets for every material decision.

### Deterministic risk governor
- Enforces hard constraints independent of the signal source.
- Can veto new entries.
- Can freeze entries.
- Can trigger flatten workflow.
- Can stop execution through kill switches.
- Owns exposure, position-size, drawdown, allowed-market, and health rules.
- Must remain testable, observable, and replayable.

### Operator update plane
- Produces periodic bot/chat/report updates while paper mode runs.
- Sends structured summaries of:
  - current mode
  - active universe
  - latest signals/proposals
  - accepted/rejected decisions
  - risk vetoes
  - paper fills
  - drawdown and exposure state
  - health/reconciliation status
  - notable incidents
- Uses mock-safe delivery by default until real webhooks or bot credentials are manually wired.

### AI/model plane
- Uses `apps/ai_router` as the only model-call entrypoint.
- Supports structured model-informed analysis and decision support.
- May produce paper-mode signal/proposal outputs when explicitly configured.
- Uses cheap/default models by default.
- Escalates to premium models only for approved offline review or evaluation jobs.
- Produces schema-validated outputs only.
- Has no unchecked authority to bypass deterministic risk policy.
- Must remain operable with mocked providers and env-var placeholders when real credentials are unavailable.

## Final module layout

```text
repo/
├─ AGENTS.md
├─ README.md
├─ Makefile
├─ pyproject.toml
├─ docker-compose.yml
├─ .env.example
├─ configs/
│  ├─ base/
│  │  ├─ app.yaml
│  │  ├─ symbols.yaml
│  │  ├─ risk.yaml
│  │  ├─ logging.yaml
│  │  └─ ai.yaml
│  ├─ dry_run/
│  │  ├─ app.yaml
│  │  └─ freqtrade.json
│  └─ live/
│     ├─ app.yaml
│     └─ freqtrade.json
├─ docs/
│  ├─ ARCHITECTURE.md
│  ├─ IMPLEMENTATION_PLAN.md
│  ├─ TASK_QUEUE.md
│  ├─ MANUAL_WIRING_CHECKLIST.md
│  ├─ RUNBOOK.md
│  ├─ INCIDENT_RESPONSE.md
│  └─ PROMOTION_CHECKLIST.md
├─ apps/
│  ├─ collector/
│  │  ├─ main.py
│  │  └─ jobs.py
│  ├─ research/
│  │  ├─ main.py
│  │  ├─ walkforward.py
│  │  └─ reports.py
│  ├─ decision_engine/
│  │  ├─ main.py
│  │  ├─ service.py
│  │  ├─ proposal_builder.py
│  │  └─ validators.py
│  ├─ supervisor/
│  │  ├─ main.py
│  │  ├─ service.py
│  │  ├─ policy.py
│  │  ├─ reconciliation.py
│  │  ├─ kill_switch.py
│  │  └─ health.py
│  ├─ ai_router/
│  │  ├─ main.py
│  │  ├─ router.py
│  │  ├─ budgets.py
│  │  ├─ prompts.py
│  │  ├─ schemas.py
│  │  ├─ providers.py
│  │  └─ usage_log.py
│  ├─ report_jobs/
│  │  ├─ daily_brief.py
│  │  ├─ weekly_review.py
│  │  ├─ nightly_rollups.py
│  │  └─ operator_update.py
│  └─ briefing_cli/
│     └─ main.py
├─ libs/
│  ├─ common/
│  │  ├─ time.py
│  │  ├─ ids.py
│  │  └─ hashing.py
│  ├─ config/
│  │  ├─ models.py
│  │  ├─ loader.py
│  │  └─ validators.py
│  ├─ market_data/
│  │  ├─ ccxt_client.py
│  │  ├─ collectors.py
│  │  ├─ normalization.py
│  │  ├─ quality_checks.py
│  │  └─ storage.py
│  ├─ strategy/
│  │  ├─ interfaces.py
│  │  ├─ universe.py
│  │  ├─ regime.py
│  │  ├─ breakout.py
│  │  ├─ sizing.py
│  │  ├─ stops.py
│  │  └─ signal_snapshot.py
│  ├─ decisioning/
│  │  ├─ schemas.py
│  │  ├─ deterministic_rules.py
│  │  ├─ model_signals.py
│  │  └─ scoring.py
│  ├─ risk/
│  │  ├─ account_policy.py
│  │  ├─ position_limits.py
│  │  ├─ drawdown_rules.py
│  │  └─ freeze_state.py
│  ├─ journal/
│  │  ├─ writer.py
│  │  ├─ schema.py
│  │  ├─ queries.py
│  │  └─ rollups.py
│  ├─ event_packets/
│  │  ├─ schemas.py
│  │  ├─ builders.py
│  │  └─ serializers.py
│  ├─ retrieval/
│  │  ├─ sqlite_fts.py
│  │  ├─ filters.py
│  │  └─ corpus_builder.py
│  ├─ notifier/
│  │  ├─ schemas.py
│  │  ├─ mock_notifier.py
│  │  └─ chat_webhook.py
│  └─ ai_costs/
│     ├─ quotas.py
│     ├─ estimators.py
│     └─ counters.py
├─ freqtrade/
│  └─ user_data/
│     ├─ strategies/
│     │  └─ regime_breakout_strategy.py
│     ├─ config.dryrun.json
│     ├─ config.live.json
│     └─ logs/
├─ scripts/
│  ├─ bootstrap_paper_runtime.py
│  ├─ bootstrap_data.py
│  ├─ update_market_data.py
│  ├─ validate_data.py
│  ├─ run_walkforward.py
│  ├─ build_signal_snapshot.py
│  ├─ reconcile_positions.py
│  ├─ freeze_entries.py
│  ├─ flatten_all.py
│  ├─ emit_daily_report.py
│  ├─ emit_operator_update.py
│  └─ replay_event_packets.py
├─ data/
│  ├─ parquet/
│  ├─ duckdb/
│  ├─ sqlite/
│  ├─ journals/
│  ├─ summaries/
│  └─ prompts/
├─ notebooks/
│  ├─ research/
│  └─ review/
└─ tests/
   ├─ unit/
   ├─ integration/
   ├─ regression/
   └─ fixtures/


   Module responsibilities
apps/collector
Use Freqtrade data-download/backtest data facilities where they satisfy the need.
Use narrow CCXT collectors only for project-specific datasets not provided by the foundation.
Persist normalized project datasets to Parquet when needed.
Run quality checks before publishing curated datasets.
libs/strategy
Pure deterministic strategy logic.
No network calls.
No filesystem writes except explicit snapshot serialization.
Single source of truth for deterministic regime, breakout, sizing, and stops.
libs/decisioning + apps/decision_engine
Build canonical decision inputs from market data, deterministic features, and configured context.
Support deterministic and model-informed proposal generation.
Validate proposal shape, confidence fields, timestamps, symbol eligibility, and stale-data rules.
Emit structured trade proposals or no-trade decisions.
Never place orders directly.
Never bypass supervisor/risk modules.
freqtrade/
Selected execution and backtesting foundation for backtest, dry-run/paper, and future live.
Calls into shared strategy/decisioning logic.
Owns exchange order lifecycle.
Must receive only validated and risk-approved intents.
Do not duplicate Freqtrade order management or exchange support in custom modules.
apps/supervisor + libs/risk
Account-level limits.
Allowed market/universe enforcement.
Max exposure and max position-size enforcement.
Drawdown limits.
Freeze/flatten controls.
Reconciliation with exchange balances and open positions.
Heartbeats and health checks.
Veto new entries when policy fails.
libs/journal
Append-only records for:
market snapshots
signal/proposal inputs
signal/proposal outputs
risk approvals and vetoes
orders
fills
balances
config hash
run ID
supervisor actions
operator updates
human overrides
libs/event_packets
Compact schemas for machine-readable downstream events:
signal generated
proposal generated
proposal rejected
risk veto
fill
reject
partial fill
stop hit
data gap
reconciliation mismatch
restart
risk freeze
kill-switch activation
operator update sent
apps/ai_router
Only entrypoint for all model calls.
Enforces schema validation, prompt versioning, provider routing, quotas, caching hooks, and usage logging.
Rejects calls that violate mode, budget, or policy.
Supports model-informed analysis/proposal jobs only through named, versioned prompts and schemas.
libs/retrieval
SQLite FTS5 index for mutable journals, summaries, incidents, and notes.
Metadata filters first, lexical retrieval second.
No managed retrieval service in v1.
libs/notifier
Mock-safe notification interface.
Optional chat/webhook delivery after manual wiring.
No secrets committed.
Delivery failures must not block execution, but must be logged.
apps/report_jobs
Nightly rollups.
Daily operator briefing.
Periodic paper-mode operator updates.
Weekly review and premium escalation jobs.
Data flow
Paper autonomous path
Exchange APIs
  -> Freqtrade data/execution shell and/or narrow CCXT collector
  -> framework data store plus Parquet / DuckDB when project artifacts are needed
  -> deterministic features + market snapshots
  -> decision_engine
  -> deterministic and/or model-informed signal/proposal generation
  -> proposal validation
  -> supervisor policy checks
  -> Freqtrade dry-run execution
  -> paper fills / balances / reconciliation
  -> journal + event packets + operator updates
Future live path
Exchange APIs
  -> Freqtrade live execution shell
  -> project snapshots / journals / event packets
  -> deterministic features + market snapshots
  -> decision_engine
  -> validated signal/proposal
  -> deterministic risk governor
  -> capped live Freqtrade execution
  -> fills / balances / reconciliation
  -> journal + event packets + alerts + operator updates

Live mode is not enabled by default. It requires promotion checklist completion, restricted credentials, capped allocation, verified kill switches, and human sign-off.

AI/model path
market snapshots + deterministic features + journal + event packets + summaries + retrieval index
  -> ai_router
  -> cheap/default model OR premium model by policy
  -> structured outputs only
  -> signal/proposal artifacts OR summaries / briefings / experiment cards / incident reviews
  -> journal + event packets
Offline research path
Freqtrade backtest data + Parquet / DuckDB
  -> Freqtrade backtesting plus project research scripts / walk-forward
  -> analysis artifacts
  -> human-reviewed strategy or model changes
  -> config / code update
  -> paper promotion gate
  -> live promotion gate
AI/model vs deterministic responsibilities
Deterministic responsibilities
Config validation.
Universe eligibility.
Stale-data detection.
Proposal schema validation.
Position sizing bounds.
Stop and risk bounds.
Balance and position reconciliation.
Risk vetoes.
Kill switches.
Freeze/flatten controls.
Promotion gating.
Audit logging.
Model-informed/autonomous responsibilities
Analyze configured market snapshots.
Generate structured trade proposals or no-trade decisions.
Explain decision rationale in bounded schema fields.
Produce summaries and operator updates.
Cluster recurring incidents.
Draft journal summaries from event packets.
Produce daily briefings.
Produce weekly post-mortems.
Propose experiments from prior results.
Assist with offline research synthesis.
Forbidden responsibilities
Bypass deterministic risk validation.
Approve its own live deployment.
Change live config without human review.
Change risk thresholds.
Mutate leverage/sizing/universe/kill-switch values.
Access live exchange credentials in sandbox, research, or offline experiment paths.
Execute live wallet trades before explicit live promotion.
Live vs paper vs offline
Paper mode
First proving ground.
Dry-run execution only.
Autonomous/model-informed decisions may be enabled if schema-validated and risk-checked.
Full journaling and event packet emission enabled.
Periodic bot/chat/report updates enabled.
AI/model jobs allowed under paper quotas.
Results must be reviewable from journals, packets, reports, and replay outputs.
Live mode
Later stage only.
Same code path as paper where possible.
Restricted credentials and small sandbox allocation.
Tighter config and risk caps.
Deterministic risk governor can veto, freeze, flatten, or kill execution.
Autonomous/model-informed signals may be consumed only after promotion gates approve that mode.
Premium AI disabled by default unless explicitly approved for offline review only.
Offline mode
Research notebooks, walk-forward tests, incident analysis, model-assisted summaries, experiment design.
Can use premium AI within explicit quotas.
No exchange write path.
No wallet credentials.
Storage model
Parquet: raw and curated market datasets.
DuckDB: analytics, walk-forward outputs, review queries.
SQLite: mutable operational state, retrieval corpus, AI usage ledger, task/job state.
Journals directory: append-only audit artifacts.
Summaries directory: AI-generated structured outputs and approved reports.
Prompt directory: versioned prompt assets.
Red lines
No unchecked model authority over live order execution.
No order path that bypasses deterministic risk policy.
No live trading before promotion checklist completion and human sign-off.
No AI-generated change applied to live config or live code without explicit human review and merge.
No premium model as default for repetitive monitoring.
No uncontrolled continuous LLM loop in live execution.
No raw long-context replay during live operation when compact packets and retrieval suffice.
No managed vector DB or agent framework in v1.
No direct news/social-to-trade path in v1.
If apps/ai_router is down, deterministic-only paper/live-safe modes must fail closed or continue according to configured mode policy.
