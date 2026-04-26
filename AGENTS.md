# AGENTS

## Purpose
This repository implements a staged autonomous crypto trading bot system whose business objective is profitable trading, constrained by deterministic risk controls, paper-first rollout, structured observability, and a later gated path toward small-capital live execution. Codex must preserve the deterministic risk governor and safety boundaries while allowing autonomous or model-informed analysis, signal generation, and paper-trading decisions where explicitly designed. Documentation and code must treat profitability as an optimization target, never as a guarantee.

## Scope boundaries

### In scope
- Market-data ingestion.
- Deterministic and model-informed analysis paths.
- Autonomous signal/proposal generation for paper trading.
- Freqtrade execution integration.
- Supervisor and deterministic risk controls.
- Journaling, event packets, alerts, reporting.
- Bot/chat/operator update delivery.
- AI router, retrieval, offline review, and model-assisted decision support.
- Promotion gates from paper mode toward future small-capital live mode.
- Tests, docs, runbooks, and deployment wiring.

### Out of scope unless explicitly requested
- New exchanges beyond the configured CEX-first path.
- Managed vector databases.
- Agent frameworks.
- Multi-agent orchestration.
- News/social ingestion for live decisions.
- Autonomous live optimization.
- Immediate live wallet execution before paper-mode promotion gates are satisfied.

## Core architecture rules
1. Preserve one execution and risk-control path used by research, paper, and future live modes.
2. Autonomous or model-informed signal generation may exist, but it must emit structured proposals/signals that pass deterministic validation and risk checks.
3. Keep exchange order placement inside the execution path only.
4. Keep account-level risk logic inside supervisor/risk modules only.
5. Keep all model calls inside `apps/ai_router` only.
6. Keep `libs/strategy` pure when implementing deterministic strategy logic: no network calls, no hidden state, no direct exchange access.
7. Keep model-informed decision modules explicit, schema-driven, logged, and replayable.
8. Prefer explicit modules and typed schemas over abstraction-heavy designs.
9. Prefer boring local infrastructure over additional services in v1.
10. Reuse the selected trading foundation where it already provides proven behavior. The current docs lean toward Freqtrade as the execution, dry-run, backtest, and later live shell; Codex should integrate and configure it before rebuilding equivalent exchange, order-lifecycle, paper-trading, or monitoring capabilities.
11. Custom engineering should focus on project-specific layers: deterministic risk governance, promotion gates, operator reporting, orchestration glue, audit/journaling, model-informed analysis boundaries, and live-readiness controls.

## Hard red lines
1. Do not give AI or any model unchecked live order authority.
2. Do not bypass the deterministic risk governor for any paper or live order path.
3. Do not allow AI to mutate live config, risk thresholds, leverage, sizing, kill-switch rules, or deployment settings without explicit human review and approval.
4. Do not add premium-model dependence to repetitive monitoring.
5. Do not make core paper/live operation depend on AI services unless the selected mode explicitly requires a model-informed decision engine and has a fail-closed fallback.
6. Do not add managed vector DBs, agent frameworks, or orchestration platforms in v1.
7. Do not duplicate shared execution/risk logic inside Freqtrade adapters.
8. Do not bypass journals or event packets for critical decisions and incidents.
9. Do not wire live wallet execution as a day-one default.
10. Do not treat live trading as approved until promotion criteria and human sign-off are complete.

## Coding rules
1. Plan first for any non-trivial task.
2. Prefer minimal patches over wide refactors.
3. Reuse existing modules before creating new ones.
4. Reuse framework capabilities before creating project-owned replacements. Only build custom functionality when it enforces project-specific safety, observability, replayability, evaluation, operator-control, or model-boundary requirements.
5. Keep functions small and explicit.
6. Add descriptive inline comments where logic is non-obvious.
7. Fail fast on invalid config or invalid state.
8. Use typed models or typed dicts for machine-readable boundaries.
9. Keep side effects at edges; keep core logic pure where possible.
10. Do not hide network calls behind utility helpers with ambiguous names.
11. Avoid optionality in implementation unless the architecture explicitly requires it.
12. Implement everything possible without external secrets, personal credentials, API keys, private account data, wallet keys, or production-only settings.
13. For secret-backed features, implement interfaces, env-var placeholders, config schema entries, mocks/fakes, tests against mocks, and manual setup notes only.
14. Do not hardcode tokens, keys, account IDs, wallet data, webhook URLs, or private endpoints.
15. Keep the repository fully runnable in mock or paper mode wherever practical.

## File placement rules
- Shared deterministic strategy logic belongs in `libs/strategy`.
- Model-informed signal/proposal logic belongs in explicit analysis/decision modules and must call models only through `apps/ai_router`.
- Risk rules belong in `libs/risk` or `apps/supervisor`.
- Market-data code belongs in `libs/market_data` and `apps/collector`.
- AI/model-routing logic belongs in `apps/ai_router`, `libs/retrieval`, or `apps/report_jobs`.
- Operator update delivery belongs in `apps/report_jobs`, `apps/briefing_cli`, or a dedicated notifier module.
- Prompt assets belong in `data/prompts/` and must be versioned.
- Operational docs belong in `docs/`.
- Secret-dependent manual steps belong in `docs/MANUAL_WIRING_CHECKLIST.md`.

## Testing expectations
1. Every non-trivial change must include or update tests.
2. Deterministic strategy changes require deterministic unit tests.
3. Model-informed signal/proposal changes require schema-validation, replay, fixture, and fail-closed tests.
4. Supervisor changes require failure-path tests.
5. Freqtrade integration changes require integration tests.
6. AI router changes require schema-validation and budget-enforcement tests.
7. Bot/chat/report delivery changes require mock-provider tests.
8. Bug fixes should include a regression test when practical.
9. End-to-end paper-mode tests must remain green before live-readiness work proceeds.

## Cost-control rules for AI-related code
1. Default to no model call unless the feature explicitly requires one.
2. Prefer deterministic preprocessing over sending raw data to a model.
3. Prefer compact event packets and retrieval over long-context dumps.
4. Default to the cheap/default model tier.
5. Use premium models only for explicit offline review jobs or approved evaluation tasks.
6. Enforce quotas and usage logging for every model call.
7. Reject model calls that lack a named prompt, version, schema, and job context.
8. Do not call models from uncontrolled hot execution loops.
9. Keep model outputs structured, logged, replayable, and subject to deterministic policy/risk checks.
10. Model-informed autonomous decisions may drive paper-trading proposals/signals only after schema validation and policy checks.

## Promotion and live-readiness rules
1. Paper trading is the first proving ground.
2. Paper-mode decisions, fills, rejects, drawdowns, risk vetoes, and operator updates must be journaled.
3. Promotion from paper to live requires saved metrics, replayable evidence, risk review, config review, and explicit human sign-off.
4. Small-capital live execution is a later implementation phase and must use restricted credentials, capped exposure, kill switches, and manual rollback procedures.
5. Future live execution may consume autonomous/model-informed signals only through deterministic validation, risk policy, promotion gates, and audit logging.
6. Live wallet credentials and webhook delivery credentials remain manual wiring points.

## Planning rules
For non-trivial work, Codex must:
1. Read the relevant files first.
2. State the intended patch surface.
3. Identify dependencies and invariants.
4. Implement the smallest complete change.
5. Run targeted tests first, then broader tests if needed.
6. Update docs when behavior or operations change.
7. Explicitly separate what can be completed now from what remains blocked on secrets or personal information.
8. Append any remaining secret-dependent setup steps to `docs/MANUAL_WIRING_CHECKLIST.md`.
9. Record completed phase or milestone progress in `ACTIVITY.MD` so the audit timeline remains synchronized with canonical `docs/` state.

## Acceptance standard
A task is complete only when:
- code matches the architecture rules,
- tests relevant to the patch pass,
- no red line is violated,
- docs/configs are updated when required,
- the deterministic risk governor remains intact,
- paper mode remains observable and replayable,
- autonomous/model-informed outputs are structured and policy-checked,
- live execution remains gated and not enabled by default,
- secret-dependent integrations are left as documented human wiring points rather than blockers.

## Additional Standing rule:
- When a milestone or phase is completed, update README.md and the relevant docs so the primary maintainer can understand how to run, inspect, and modify the system.
