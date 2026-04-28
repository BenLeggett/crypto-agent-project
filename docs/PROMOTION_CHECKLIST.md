# Promotion Checklist Draft

This checklist defines the evidence needed to consider promotion from paper mode
toward a later live-readiness review. It is not live approval, does not permit
live wallet execution, and does not replace explicit human sign-off.

## Scope

- Review only paper-mode or offline evidence.
- Keep the deterministic risk governor authoritative over hard constraints.
- Treat profitability as an optimization target constrained by risk, evidence,
  replayability, and operator visibility.
- Do not wire live credentials or enable live execution from this checklist.

## Required Paper Evidence

- Paper run IDs, date ranges, config hashes, and selected universe are recorded.
- Daily reports exist for the reviewed period under `data/summaries/` or another
  documented local artifact path.
- Append-only journals and event packets exist for proposals, risk decisions,
  vetoes, fills, restarts, freezes, mismatches, and operator updates.
- Replay output can reconstruct decision and incident timelines for each
  reviewed run ID.
- Restart recovery evidence shows state was not corrupted.
- Data-gap evidence shows corrupt or missing market data failed closed before
  decisioning or execution.
- Risk-veto evidence shows vetoed proposals did not create orders or fills.
- Drawdown review covers peak drawdown, daily drawdown, exposure, position
  sizing, and any freeze or kill-switch events.
- Reconciliation review covers mismatches and the operator-facing explanation
  for each unresolved case.
- Operator update evidence shows paper-mode status can be reviewed locally or
  through mock-safe delivery.
- Model-informed proposal modes, if enabled later, must have schema validation,
  replay fixtures, quota evidence, and deterministic risk checks before any
  promotion discussion.

## Explicit Non-Approval

- This draft does not approve live trading.
- This draft does not approve exchange API keys, wallet funding, webhook
  credentials, or Freqtrade live configuration.
- This draft does not allow AI or model-informed outputs to bypass deterministic
  proposal validation, risk policy, promotion gates, or audit logging.
- Future live approval requires a separate Phase 14/15 review, restricted
  credentials, capped exposure, safety drills, rollback procedures, and explicit
  human sign-off.

## Review Decision Template

- Run IDs reviewed:
- Evidence window:
- Config hashes reviewed:
- Daily report artifact paths:
- Replay artifact paths:
- Risk veto summary:
- Drawdown and exposure summary:
- Reconciliation summary:
- Operator update summary:
- Open incidents:
- Required follow-up before live-readiness review:
- Reviewer:
- Decision: `continue_paper`, `extend_paper_review`, or `ready_for_live_readiness_review`
