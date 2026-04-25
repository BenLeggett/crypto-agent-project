# Manual Wiring Checklist

Use this file for any setup Codex cannot complete without external secrets, personal credentials, private account data, wallet credentials, webhook URLs, or other human-supplied values.

## Instructions
- Append new items; do not delete completed history unless a human chooses to clean it up.
- Reference the exact file(s), env var name(s), and validation rule(s) involved.
- Prefer placeholders, mocks, and fake providers in code until a human wires the real values.
- Mark each item as `pending`, `completed`, or `not_applicable`.
- Live wallet/exchange wiring is a later-stage task and must not enable live execution by default.
- Bot/chat delivery wiring should use mock delivery until a human provides approved webhook or bot credentials.

## Template

### Item
- Status: `pending`
- Area:
- Reason human input is required:
- File(s):
- Env var(s) / secret name(s):
- Expected format:
- Placeholder or mock already implemented:
- Validation / failure behavior if missing:
- Manual steps for human:
- Verification steps after wiring:
- Notes:

## Initial entries

### Item
- Status: `pending`
- Area: Exchange/API credentials
- Reason human input is required: Real credentials, account identifiers, wallet/exchange permissions, and trading limits cannot be generated or inferred safely.
- File(s): `.env`, `configs/live/*`, exchange adapter wiring
- Env var(s) / secret name(s): `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`, `EXCHANGE_API_PASSPHRASE`
- Expected format: Provider-issued credential strings; passphrase only if required by the selected venue.
- Placeholder or mock already implemented: Use `.env.example` placeholders and mocked provider behavior until live wiring.
- Validation / failure behavior if missing: Live or credential-backed integration paths must fail closed with a clear configuration error.
- Manual steps for human: Create restricted credentials, place values in the local secret store or `.env`, and confirm venue permissions match the intended mode.
- Verification steps after wiring: Run config validation, a read-only connectivity check if implemented, and confirm mock mode is no longer selected for the target environment.
- Notes: Never commit real credentials or account identifiers. Live trading remains unavailable until promotion criteria and human sign-off are complete.

### Item
- Status: `pending`
- Area: AI provider credentials
- Reason human input is required: Provider API keys and organization/project settings are user-owned secrets.
- File(s): `.env`, `configs/base/ai.yaml`, `apps/ai_router/providers.py`
- Env var(s) / secret name(s): `OPENAI_API_KEY`, provider-specific alternatives as approved by the project docs
- Expected format: Provider-issued API key string.
- Placeholder or mock already implemented: Mock providers and fake responses should remain available for local development and tests.
- Validation / failure behavior if missing: Model-backed jobs using real providers must fail closed and log a clear missing-secret error; deterministic-only trading paths must continue to function according to configured mode.
- Manual steps for human: Add the approved provider key to the local secret store or `.env` and select the intended provider/model tier in config.
- Verification steps after wiring: Run AI router policy tests or a provider smoke test against a non-production job path.
- Notes: Premium models remain opt-in and offline/review-oriented unless later approved in project docs.

### Item
- Status: `pending`
- Area: Bot/chat/report delivery credentials
- Reason human input is required: Webhook URLs, bot tokens, channel IDs, and chat workspace permissions are external user-owned values.
- File(s): `.env`, `configs/base/app.yaml`, `apps/report_jobs/operator_update.py`, `libs/notifier/*`
- Env var(s) / secret name(s): `OPERATOR_UPDATE_WEBHOOK_URL`, `OPERATOR_UPDATE_BOT_TOKEN`, `OPERATOR_UPDATE_CHANNEL_ID`
- Expected format: Provider-specific webhook URL, bot token, or channel identifier.
- Placeholder or mock already implemented: Use mock notifier and local report output until real delivery credentials are wired.
- Validation / failure behavior if missing: Operator update jobs should write local report artifacts and log that external delivery is not configured; trading state must not be blocked or corrupted.
- Manual steps for human: Create or approve the chat/bot/webhook integration, place credentials in the local secret store or `.env`, and select the notifier provider in config.
- Verification steps after wiring: Run a test operator update against a non-production channel and confirm delivery, formatting, and failure logging.
- Notes: Do not commit webhook URLs, bot tokens, or channel IDs.

### Item
- Status: `pending`
- Area: Future live wallet / small-capital allocation
- Reason human input is required: Wallet funding, capital allocation, exchange permissions, withdrawal settings, and legal/account ownership details are human-owned decisions.
- File(s): `.env`, `configs/live/*`, `freqtrade/user_data/config.live.json`, `docs/PROMOTION_CHECKLIST.md`, `docs/RUNBOOK.md`
- Env var(s) / secret name(s): `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`, `EXCHANGE_API_PASSPHRASE`, any venue-specific wallet/account identifiers
- Expected format: Restricted exchange credentials with only the permissions required for the approved live mode.
- Placeholder or mock already implemented: Live config should exist with placeholders only; paper mode and mock providers should remain the default.
- Validation / failure behavior if missing: Live mode must fail closed unless credentials, promotion marker, live caps, and explicit mode flags are present.
- Manual steps for human: Complete paper-mode review, approve promotion checklist, create restricted credentials, allocate only the approved sandbox capital amount, disable unnecessary permissions where possible, and confirm rollback/kill-switch procedures.
- Verification steps after wiring: Run config validation, read-only exchange connectivity check, reconciliation check, alert delivery test, and kill-switch drill before allowing any write-enabled live session.
- Notes: This is a later-stage integration. Do not treat live wallet execution as available on day one.