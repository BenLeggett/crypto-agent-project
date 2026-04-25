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
