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
