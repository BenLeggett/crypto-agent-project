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
