.PHONY: test test-unit smoke data-bootstrap data-update

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
