.PHONY: test test-unit smoke data-bootstrap data-update data-validate freqtrade-backtest freqtrade-dryrun

test:
	python -m pytest

test-unit:
	python -m pytest tests/unit

smoke:
	python -m pytest tests/unit/test_repo_skeleton_imports.py

data-bootstrap:
	python scripts/bootstrap_data.py $(ARGS)

data-update:
	python scripts/update_market_data.py $(ARGS)

data-validate:
	python scripts/validate_data.py $(ARGS)

freqtrade-backtest:
	python scripts/run_freqtrade_backtest.py $(ARGS)

freqtrade-dryrun:
	python scripts/run_freqtrade_dryrun.py $(ARGS)
