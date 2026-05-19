# Crypto Agent Project

This repository is a paper-first autonomous crypto trading system scaffold.
The current implementation is intentionally inert: packages import, placeholder
entrypoints boot locally, and no exchange, model, wallet, or notifier network
call is made.

The business objective is profitable trading over time. Profitability is treated
as an optimization target constrained by deterministic risk limits, paper-mode
evidence, observability, and staged promotion gates; it is not guaranteed.

The practical build path is Freqtrade-first: use Freqtrade for solved
backtesting, dry-run/paper execution, exchange order lifecycle, and future gated
live execution where appropriate. Custom code should stay focused on the
project-specific layers: risk governance, promotion gates, reporting,
orchestration, audit/journaling, model-informed analysis boundaries, and
live-readiness controls.

## Current Slice

- Repo skeleton and canonical module layout are present.
- `docs/` contains the architecture, implementation plan, task queue, and manual
  wiring checklist.
- Paper/dry-run remains the default posture.
- Live execution is not enabled and remains gated by future promotion criteria,
  credentials, capped risk settings, and human sign-off.

## Local Development

Install test dependencies in your preferred environment, then run:

```bash
python -m pytest
```

Optional market-data storage dependencies are only needed when writing real
Parquet files or registering DuckDB analytics views:

```bash
python -m pip install -e ".[market-data]"
```

Useful targets:

```bash
make smoke
make test-unit
make test
```

## Agent Orchestrator Operator Controls

The local development orchestrator lives under `agent-orchestrator/`. Its
validator remains deterministic and model-free; local LLM output is advisory
operator guidance only.

For first-time operation, setup, command reference, auto-mode expectations, and
testing steps, read
`agent-orchestrator/docs/ORCHESTRATOR_USAGE_GUIDE.md`.
Before leaving Mode B unattended, follow
`agent-orchestrator/docs/MODE_B_UNATTENDED_READINESS_CHECKLIST.md`.

Run the Discord listener in mock stdin mode when no bot token is wired:

```bash
python agent-orchestrator/discord_listener.py
```

Supported operator commands are `!status`, `!approve <ref>`, `!reject <ref>
<notes>`, `!pause`, `!resume`, read-only `!explain`, `!clarify <task_id>
<details>`, and `!skip-task <task_id>`. In Discord mode, only the latest
bot-owned message has action buttons. Failed idle tasks also show a
`Deep Diagnose` button for explicit medium-model review. Stage 12D Codex states
surface as dashboard-specific statuses and actions: clarification states show a
`Clarify Task <id>` modal button plus `Skip Task <id>`, while timeout or Codex
failure review states show retry/skip actions.

Stage 12D Mode B automation invokes Codex with `codex exec` over stdin after
orchestrator gates pass. Generated `agent-orchestrator/last_prompt.md` files
start with a strict Codex task contract; auto mode lints that contract before
launch, captures Codex's final response in `codex_last_message.md`, pauses on
timeouts, non-zero exits, validation failures, or clarification markers, and
limits successful auto cycles with `MAX_AUTO_TASKS_PER_SESSION`. Safe defaults
remain documented in `agent-orchestrator/.env.example`, with `CODEX_MODE=manual`
until the operator explicitly enables auto mode.

Slow typed commands post action-specific progress text first with no buttons,
then replace it with the result and buttons. Button clicks use Discord's native
bot-is-thinking indicator while the request is in flight, then post the final
response with buttons. Long Discord responses are split across multiple messages
instead of being silently cut to one message; buttons attach only to the final
message. When old buttons are removed, the old bot message is annotated with
the action selected and the current wait target.

The `!explain` command summarizes current SQLite status, recent `ACTIVITY.MD`,
paused state, the latest advisory diagnosis, and a `last_prompt.md` excerpt
through the local low model. If
the model call fails, it returns a deterministic explanation plus the local
model failure reason. A reachable `/v1/models` endpoint proves the server is up,
but the chat call can still fail if the configured model name does not match an
installed Ollama model, if `/chat/completions` rejects the request, or if the
model load exceeds the configured tier timeout. Routine operator summaries use
the low local model with `LOCAL_LLM_LOW_TIMEOUT_SECONDS` and
`LOCAL_LLM_LOW_MAX_TOKENS`; automatic validation-failure diagnosis uses the low
model asynchronously after the deterministic loop has already marked the task
failed and paused. `Deep Diagnose` warms and reviews with the medium model using
`LOCAL_LLM_MEDIUM_WARMUP_TIMEOUT_SECONDS`,
`LOCAL_LLM_MEDIUM_TIMEOUT_SECONDS`, and `LOCAL_LLM_MEDIUM_MAX_TOKENS`. Ollama
residency is requested with `LOCAL_LLM_LOW_KEEP_ALIVE` and
`LOCAL_LLM_MEDIUM_KEEP_ALIVE`; the listener preloads local models on startup
when `LOCAL_LLM_PRELOAD_ON_START=true`. Local calls retry according to
`LOCAL_LLM_RETRY_ATTEMPTS`; webhook delivery retries transient Discord `429`
and `5xx` responses according to `DISCORD_WEBHOOK_RETRY_ATTEMPTS`.

The Discord listener renders one evolving task run card from durable
`operator_events` stored in `state.sqlite`; routine run-loop state changes no
longer post separate webhook messages into the channel. In Discord mode the card
is rendered as an embed with separate status, progress, current-step, finding,
and next-action fields so the layout stays readable as text changes. Button
interactions always complete their deferred Discord response, which prevents the
native thinking indicator from hanging after the card updates. During validation
and explicit medium review, card buttons are hidden and `!explain` is blocked so
the low model does not compete with active review work. Failed tasks still
remain `failed`, the loop still sets `paused=1`, and `!resume` only means the
operator is ready to re-run validation. Empty model responses are treated as
unavailable rather than posted as blank diagnoses.

Secrets are never required for this slice. Use `.env.example` as a placeholder
reference only; real credentials belong in local secret storage or an untracked
`.env` when later manual wiring steps are approved.

## Configuration

Configuration loads from `configs/base/` plus an environment overlay selected by
`CONFIG_ENV`; the safe default is `dry_run`. The loader also accepts explicit
environment overrides such as `SYMBOLS`, `TIMEFRAMES`, `LOG_LEVEL`, and
`AI_PROVIDER`.

Live config is present only as a gated future path. In this foundation slice,
any attempt to set live execution enabled fails closed during config validation.
Real AI providers require their matching secret env var, while the default
`mock` provider requires no secret.

## Logging

App entrypoints use shared logging from `libs/common/logging.py`. The default
format is structured JSON from `configs/base/logging.yaml`, and each startup log
includes `service_name` and `run_id` fields for later journaling, reporting, and
operator diagnostics.

## Market Data Boundary

`libs/market_data/ccxt_client.py` provides a narrow read-only wrapper for
project-specific OHLCV and market metadata reads. It is mock-first and does not
require secrets. Freqtrade remains the preferred foundation for solved data,
backtest, dry-run, and execution workflows where it fits.

Historical OHLCV bootstrap and incremental update jobs now build explicit
Freqtrade `download-data` commands through an injectable command runner. Tests
use mocks, so no Freqtrade install, exchange network access, or credentials are
required for validation.

Example command shape once Freqtrade is installed locally:

```bash
make data-bootstrap ARGS="--symbols BTC/USDT ETH/USDT --timeframes 1h 4h --exchange binance"
make data-update ARGS="--symbols BTC/USDT --timeframes 1h --days 7 --exchange binance"
```

`libs/market_data/storage.py` provides the project-owned storage boundary for
raw and curated OHLCV datasets. It writes Parquet through `pyarrow` and
registers queryable DuckDB views when the optional `market-data` extra is
installed. Unit tests use fake backends, so storage behavior remains verifiable
without external packages or secrets.

`libs/market_data/normalization.py` and `libs/market_data/quality_checks.py`
validate project-owned OHLCV datasets before curated promotion. They detect
missing fields, duplicate timestamps, out-of-order rows, candle gaps, negative
values, and malformed candle ranges. The local validation script can be run
against a Parquet file when optional market-data dependencies are installed:

```bash
make data-validate ARGS="--path data/parquet/raw/ohlcv/BTC_USDT/1h.parquet"
```

## Deterministic Strategy Library

`libs/strategy/` contains the shared pure strategy core for universe selection,
daily regime classification, 4h breakout signals, sizing, stops, and canonical
signal snapshots. These modules do not call exchanges, Freqtrade runtime,
models, notifiers, wallets, or the filesystem during strategy evaluation.

Fixture-backed strategy tests can be run locally without secrets:

```bash
python -m pytest tests/unit/test_strategy_fixture_determinism.py
```

## Research Helpers

`apps/research/reports.py` can turn saved Freqtrade backtest JSON into a
versioned project metrics artifact for later evaluation and promotion review.
This does not run live trading, does not require credentials, and does not treat
backtest profitability as live approval.

Example after producing a local Freqtrade backtest export:

```bash
python -m apps.research.main backtest-report --input path/to/backtest-result.json --output-dir data/summaries/research
```

The walk-forward wrapper can evaluate multiple saved backtest result files as
explicit train/test splits and writes a versioned run manifest plus per-split
metric artifacts:

```bash
python scripts/run_walkforward.py \
  --split fold1,path/to/fold1-backtest.json,2024-01-01,2024-01-31,2024-02-01,2024-02-29 \
  --split fold2,path/to/fold2-backtest.json,2024-03-01,2024-03-31,2024-04-01,2024-04-30 \
  --output-dir data/summaries/research \
  --run-id wf_local_review
```

For one saved backtest file without split metadata, the compatibility path still
emits a single metrics artifact:

```bash
python scripts/run_walkforward.py --backtest-result path/to/backtest-result.json --output-dir data/summaries/research
```

Phase 4 research tests are fully local and fixture-backed:

```bash
python -m pytest tests/unit/test_research_reports.py tests/unit/test_walkforward.py tests/regression/test_research_metrics.py
```

## Decision Schema Boundary

`libs/decisioning/schemas.py` defines the first Phase 5 machine-readable
boundary for autonomous paper decisioning: market snapshots, decision inputs,
trade proposals, no-trade decisions, and proposal rejections. These records are
typed, versioned, serializable, and intentionally cannot place orders. Any
proposal from deterministic or future model-informed logic must still pass
deterministic validation and later supervisor/risk checks before paper
execution.

Schema tests run locally without secrets:

```bash
python -m pytest tests/unit/test_decision_schemas.py
```

The deterministic proposal builder converts pure strategy snapshots into
canonical proposal or no-trade records only. It does not place orders; proposals
remain subject to deterministic validation and later supervisor/risk checks.

```bash
python -m pytest tests/unit/test_deterministic_proposal_builder.py
```

Task 22 adds explicit proposal validation reports for stale market snapshots,
expired proposals, out-of-universe symbols, and proposal-level size bounds. This
is a fail-closed pre-risk boundary only; the supervisor remains authoritative for
account-level hard constraints before paper or future live execution.

```bash
python -m pytest tests/unit/test_decision_validation.py
```

Decision-engine replay fixtures live under `tests/fixtures/decisioning/` and
prove fixed strategy snapshots replay to identical proposal records.

```bash
python -m pytest tests/unit/test_decision_engine.py
```

## Freqtrade Strategy Adapter

`freqtrade/user_data/strategies/regime_breakout_strategy.py` now provides the
Task 24 adapter surface between Freqtrade-style candle frames and the shared
deterministic strategy/decisioning modules. It converts OHLCV rows into
`libs.strategy` contracts, builds canonical strategy snapshots, and emits
paper-mode proposal/no-trade records through the existing decision schema.

The adapter is import-safe without Freqtrade installed, so local tests can run
with mocked/pandas candle frames and no exchange credentials:

```bash
python -m pytest tests/unit/test_freqtrade_strategy_adapter.py
```

Freqtrade entry columns remain disabled by default until the later supervisor
and deterministic risk-governor integration can approve intents before dry-run
or future live execution. Live wallet execution is still not approved or wired.

## Freqtrade Configs And Wrappers

Task 25 adds dry-run-first Freqtrade config templates plus explicit wrapper
commands for local backtesting and paper-mode dry-run startup. The wrappers call
Freqtrade directly, without shell interpolation, and reject live config paths.

```bash
make freqtrade-backtest ARGS="--timerange 20240101-20240201 --timeframe 4h"
make freqtrade-dryrun
```

These commands require Freqtrade to be installed locally when actually run.
Unit tests validate the command shape with fakes, so no exchange credentials,
wallet keys, Telegram token, Web UI password, or live account data are required
for repository validation.

The live Freqtrade template remains a future gated path only: it is not the
default, starts stopped, uses placeholders, keeps optional operator surfaces
disabled, and is not accepted by the Task 25 wrappers.

Phase 6 integration coverage verifies the adapter, dry-run config, and wrapper
command boundaries together with local fixtures and fake runners:

```bash
python -m pytest tests/integration/test_freqtrade_adapter.py
```

## Deterministic Risk Policy

Task 27 adds the first account-level deterministic risk policy in `libs/risk/`.
It evaluates structured trade proposals against allowed markets, entry freeze
state, kill switch state, drawdown limits, max order notional, per-symbol
exposure, and total exposure. The policy returns versioned allow/veto records
with stable reasons and does not place orders, call exchanges, read secrets, or
enable live execution.

Risk policy tests run locally without credentials:

```bash
python -m pytest tests/unit/test_risk_policy.py
```

## Supervisor Service

Task 28 adds the supervisor service foundation in `apps/supervisor/`. It wraps
the deterministic risk policy, evaluates structured paper-mode proposals,
reports supervisor health, and treats entry freeze, drawdown breaches, and kill
switch state as machine-readable operational status. It still does not place
orders, call exchanges, read secrets, flatten positions, or enable live
execution.

Supervisor tests run locally without credentials:

```bash
python -m pytest tests/unit/test_supervisor_service.py
```

## Freeze And Kill-Switch Controls

Task 29 adds deterministic supervisor controls for freezing entries, activating
the kill switch, and requesting flatten workflows. These controls emit
structured records only. They do not place orders, contact exchanges, wire
Freqtrade runtime commands, use wallet credentials, or enable live execution.

Local command examples:

```bash
python scripts/freeze_entries.py --reason "paper drawdown review"
python scripts/flatten_all.py --reason "paper safety drill"
```

Freeze and flatten control tests run locally without secrets:

```bash
python -m pytest tests/unit/test_freeze_controls.py
```

## Supervisor Alert Boundary

Phase 7 alert hooks live in `apps/supervisor/alerts.py`. They convert risk
vetoes, degraded/stopped health, entry freezes, kill-switch activation,
non-executing flatten requests, and reconciliation mismatches into versioned
JSON-compatible records. The default sink is an in-memory mock, and delivery
failures return structured delivery records instead of blocking supervisor,
risk, freeze, flatten, or reconciliation flow.

These hooks are intentionally local and pluggable. Real webhook, bot, chat, or
Freqtrade-native operator delivery remains a later manual wiring point and is
not required for Phase 7 validation.

```bash
python -m pytest tests/unit/test_supervisor_alerts.py
```

## Reconciliation Flow

Task 30 adds deterministic reconciliation for comparing internal account state
against externally supplied account snapshots. The comparator classifies balance
and position mismatches and emits a versioned JSON report. It does not fetch
exchange data, read credentials, repair state, place orders, or enable live
execution.

Local command shape:

```bash
python scripts/reconcile_positions.py \
  --internal-snapshot path/to/internal_snapshot.json \
  --external-snapshot path/to/external_snapshot.json
```

Without snapshot files the command compares empty mock snapshots, which is only
useful as a local smoke check.

Reconciliation tests run locally without secrets:

```bash
python -m pytest tests/unit/test_reconciliation.py
```

## Phase 7 Supervisor Validation

Task 31 adds integration coverage across the deterministic supervisor stack:
policy vetoes, entry freeze, kill switch, non-executing flatten requests,
reconciliation mismatches, degraded-health paths, and mock-safe alert records.
When Phase 7 says supervisor decisions are "logged," that means structured
JSON-compatible records and mock delivery results. Phase 8 adds the append-only
journal writer, event packet schemas, and replay utility that turn those records
into durable audit streams. The tests use local typed records only and do not
require exchange credentials, notifier credentials, Freqtrade runtime access,
wallet access, or live execution.

```bash
python -m pytest tests/integration/test_supervisor.py tests/unit/test_supervisor_alerts.py
```

## Append-Only Journal Foundation

Task 32 adds the local audit record schema and append-only JSONL writer in
`libs/journal/`. `JournalRecord` validates run IDs, millisecond timestamps,
record types, source names, config hashes, metadata, and JSON-serializable
payloads before anything is written. `JournalWriter` creates local parent
directories, appends one compact JSON object per line, and returns write
metadata including line number, byte offset, and content hash.

This is local filesystem journaling only. It does not call exchanges, models,
webhooks, wallets, or Freqtrade, and it does not enable live execution. Later
Phase 8 tasks add event packet schemas, integration wiring from decisioning and
supervisor flows, and replay utilities.

```bash
python -m pytest tests/unit/test_journal_writer.py
```

## Event Packet Foundation

Task 33 adds compact, versioned event packet schemas, builders, and serializers
in `libs/event_packets/`. Packets cover proposal generated/rejected events,
risk decisions and vetoes, fills, order rejects, restarts, risk freezes,
kill-switch activation, and reconciliation mismatches. They serialize to
deterministic JSON or JSONL lines for later reporting, retrieval, and replay.

This task only defines packet records and pure builders. It does not emit
packets from decisioning, supervisor, Freqtrade, or execution paths yet, and it
does not write journals or enable live execution. Runtime wiring is a later
Phase 8 task.

```bash
python -m pytest tests/unit/test_event_packets.py
```

## Audit Wiring Foundation

Task 34 wires the journal and event-packet primitives into the current local
decisioning, supervisor, reconciliation, control, and Freqtrade adapter
surfaces. Decision results now produce proposal input/output journal records
and proposal packets. Supervisor evaluations produce risk-decision journal
records and risk-decision or risk-veto packets. Freeze, kill-switch, flatten,
and reconciliation mismatch helpers produce matching local audit artifacts.
The Freqtrade adapter annotates its latest candle with decision records,
journal records, and event packets while keeping entries disabled by default.

This is still local artifact generation only. It does not call exchanges,
models, webhooks, wallets, or live Freqtrade execution; it does not persist
anything unless the local journal writer is explicitly used by a caller. Replay
utilities and paper-mode runtime composition remain later tasks.

```bash
python -m pytest tests/unit/test_audit_wiring.py tests/integration/test_freqtrade_adapter.py
```

## Replay Utility

Task 35 adds `scripts/replay_event_packets.py` for local reconstruction of
decision and incident timelines from append-only journal JSONL files and event
packet JSONL files. The utility reads files only, filters by run ID or
millisecond timestamp range, and emits deterministic JSON for operator review,
tests, retrieval, and later promotion evidence.

```bash
python scripts/replay_event_packets.py \
  --journal-path data/journals/paper-run.jsonl \
  --packet-path data/event_packets/paper-run.jsonl \
  --run-id paper-run-001 \
  --pretty
```

Replay tests are fully local and require no credentials, webhooks, exchange
access, model calls, wallet access, or live execution:

```bash
python -m pytest tests/unit/test_replay_event_packets.py
```

## Paper Compose Stack

Task 36 adds the first paper-mode compose setup. `docker-compose.yml` starts a
local audit bootstrap, the decision-engine boundary, the deterministic
supervisor, and Freqtrade dry-run with the checked-in dry-run config. The audit
bootstrap writes local restart records to `data/journals/paper-runtime.jsonl`
and `data/event_packets/paper-runtime.jsonl` before the long-running services
start.

```bash
make paper-up
```

Useful local follow-ups:

```bash
make paper-logs
make paper-replay
make paper-down
```

This stack is paper/dry-run only. It uses `freqtrade/user_data/config.dryrun.json`,
keeps live execution flags false, keeps AI provider mode mocked, and does not
require exchange keys, wallet credentials, bot tokens, or webhook URLs. Docker
must be able to pull the configured Python and Freqtrade images, and Freqtrade
dry-run may need public exchange connectivity for market data, but those are not
secret-backed live wiring steps.

Task 37 is still responsible for end-to-end paper tests covering restart
recovery, data gaps, risk vetoes, and steady-state operation.

```bash
python -m pytest tests/unit/test_paper_runtime_bootstrap.py tests/unit/test_paper_compose_config.py
```

## Paper End-To-End Tests

Task 37 adds CI-friendly paper-mode integration tests that exercise the local
paper stack boundaries without Docker, exchange credentials, wallet access, AI
provider keys, bot tokens, or webhook URLs. The tests cover restart recovery,
data-gap blocking, deterministic supervisor risk vetoes, and steady-state
dry-run guardrails using journal records, event packets, and replay output.

```bash
python -m pytest tests/integration/test_paper_mode_e2e.py
```

## Paper Daily Report

Phase 9 includes a mock/local daily report artifact built from existing journal
and event packet streams through the replay utility. The report is JSON, writes
to `data/summaries/daily_report.json` by default, and is evidence for paper-mode
review only. It is not live trading approval.

```bash
python scripts/emit_daily_report.py --run-id paper-local --pretty
```

The draft promotion evidence checklist lives at
`docs/PROMOTION_CHECKLIST.md`. It focuses on paper-mode evidence, risk vetoes,
replayability, drawdown review, operator updates, and explicit future human
approval before any live wiring.
