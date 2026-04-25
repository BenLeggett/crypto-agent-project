# Manual Wiring Checklist

Use this file for any setup Codex cannot complete without external secrets, personal credentials, private account data, or other human-supplied values.

## Instructions
- Append new items; do not delete completed history unless a human chooses to clean it up.
- Reference the exact file(s), env var name(s), and validation rule(s) involved.
- Prefer placeholders, mocks, and fake providers in code until a human wires the real values.
- Mark each item as `pending`, `completed`, or `not_applicable`.

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
- Reason human input is required: Real credentials, account identifiers, and permissions cannot be generated or inferred safely.
- File(s): `.env`, `configs/live/*`, exchange adapter wiring
- Env var(s) / secret name(s): `EXCHANGE_API_KEY`, `EXCHANGE_API_SECRET`, `EXCHANGE_API_PASSPHRASE`
- Expected format: Provider-issued credential strings; passphrase only if required by the selected venue.
- Placeholder or mock already implemented: Use `.env.example` placeholders and mocked provider behavior until live wiring.
- Validation / failure behavior if missing: Live or credential-backed integration paths must fail closed with a clear configuration error.
- Manual steps for human: Create restricted credentials, place values in the local secret store or `.env`, and confirm venue permissions match the intended mode.
- Verification steps after wiring: Run config validation, a read-only connectivity check if implemented, and confirm mock mode is no longer selected for the target environment.
- Notes: Never commit real credentials or account identifiers.

### Item
- Status: `pending`
- Area: AI provider credentials
- Reason human input is required: Provider API keys and organization/project settings are user-owned secrets.
- File(s): `.env`, `configs/base/ai.yaml`, `apps/ai_router/providers.py`
- Env var(s) / secret name(s): `OPENAI_API_KEY`, provider-specific alternatives as approved by the project docs
- Expected format: Provider-issued API key string.
- Placeholder or mock already implemented: Mock providers and fake responses should remain available for local development and tests.
- Validation / failure behavior if missing: Advisory jobs using real providers must fail closed and log a clear missing-secret error; deterministic trading paths must continue to function.
- Manual steps for human: Add the approved provider key to the local secret store or `.env` and select the intended provider/model tier in config.
- Verification steps after wiring: Run AI router policy tests or a provider smoke test against a non-production job path.
- Notes: Premium models remain opt-in and offline-only unless later approved in project docs.
