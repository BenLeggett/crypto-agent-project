# AGENTS

## Purpose
This repository implements a deterministic, risk-controlled crypto trading system with an asynchronous low-cost AI advisory layer. Codex must preserve the deterministic execution core and must not introduce AI into the live execution path.

## Scope boundaries

### In scope
- Deterministic market-data ingestion.
- Deterministic strategy logic.
- Freqtrade execution integration.
- Supervisor and risk controls.
- Journaling, event packets, alerts, reporting.
- AI router, retrieval, and offline/advisory jobs.
- Tests, docs, runbooks, and deployment wiring.

### Out of scope unless explicitly requested
- New strategy families.
- New exchanges beyond the configured CEX-first path.
- Managed vector databases.
- Agent frameworks.
- Multi-agent orchestration.
- Continuous AI loops.
- News/social ingestion for live decisions.
- Autonomous live optimization.

## Core architecture rules
1. Preserve one deterministic trading core used by research, paper, and live.
2. Keep exchange order placement inside the execution path only.
3. Keep account-level risk logic inside supervisor/risk modules only.
4. Keep all model calls inside `apps/ai_router` only.
5. Keep `libs/strategy` pure: no network calls, no hidden state, no direct exchange access.
6. Prefer explicit modules and typed schemas over abstraction-heavy designs.
7. Prefer boring local infrastructure over additional services in v1.

## Hard red lines
1. Do not add any model call between deterministic signal generation and order execution.
2. Do not give AI unchecked live order authority.
3. Do not allow AI to mutate live config, risk thresholds, leverage, sizing, kill-switch rules, or deployment settings.
4. Do not add premium-model dependence to repetitive monitoring.
5. Do not make paper/live operation depend on AI services.
6. Do not add managed vector DBs, agent frameworks, or orchestration platforms in v1.
7. Do not duplicate strategy logic inside Freqtrade adapters.
8. Do not bypass journals or event packets for critical decisions and incidents.

## Coding rules
1. Plan first for any non-trivial task.
2. Prefer minimal patches over wide refactors.
3. Reuse existing modules before creating new ones.
4. Keep functions small and explicit.
5. Add descriptive inline comments where logic is non-obvious.
6. Fail fast on invalid config or invalid state.
7. Use typed models or typed dicts for machine-readable boundaries.
8. Keep side effects at edges; keep core logic pure.
9. Do not hide network calls behind utility helpers with ambiguous names.
10. Avoid optionality in implementation unless the architecture explicitly requires it.
11. Implement everything possible without external secrets, personal credentials, API keys, private account data, or production-only settings.
12. For secret-backed features, implement interfaces, env-var placeholders, config schema entries, mocks/fakes, tests against mocks, and manual setup notes only.
13. Do not hardcode tokens, keys, account IDs, wallet data, webhook URLs, or private endpoints.
14. Keep the repository fully runnable in mock mode wherever practical.

## File placement rules
- Shared deterministic logic belongs in `libs/strategy`.
- Risk rules belong in `libs/risk` or `apps/supervisor`.
- Market-data code belongs in `libs/market_data` and `apps/collector`.
- AI logic belongs in `apps/ai_router`, `libs/retrieval`, or `apps/report_jobs`.
- Prompt assets belong in `data/prompts/` and must be versioned.
- Operational docs belong in `docs/`.
- Secret-dependent manual steps belong in `docs/MANUAL_WIRING_CHECKLIST.md`.

## Testing expectations
1. Every non-trivial change must include or update tests.
2. Strategy changes require deterministic unit tests.
3. Supervisor changes require failure-path tests.
4. Freqtrade integration changes require integration tests.
5. AI router changes require schema-validation and budget-enforcement tests.
6. Bug fixes should include a regression test when practical.
7. End-to-end paper-mode tests must remain green before live-readiness work proceeds.

## Cost-control rules for AI-related code
1. Default to no model call unless the feature explicitly requires one.
2. Prefer deterministic preprocessing over sending raw data to a model.
3. Prefer compact event packets and retrieval over long-context dumps.
4. Default to the cheap/default model tier.
5. Use premium models only for explicit offline review jobs.
6. Enforce quotas and usage logging for every model call.
7. Reject model calls that lack a named prompt, version, schema, and job context.
8. Never call models from hot execution loops.
9. Keep AI outputs advisory unless a human explicitly reviews and applies them.

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

## Acceptance standard
A task is complete only when:
- code matches the architecture rules,
- tests relevant to the patch pass,
- no red line is violated,
- docs/configs are updated when required,
- the deterministic paper/live path remains intact without AI,
- secret-dependent integrations are left as documented human wiring points rather than blockers.
