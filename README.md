# Crypto Agent Project

This repository is a paper-first autonomous crypto trading system scaffold.
The current implementation is intentionally inert: packages import, placeholder
entrypoints boot locally, and no exchange, model, wallet, or notifier network
call is made.

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

Useful targets:

```bash
make smoke
make test-unit
make test
```

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
