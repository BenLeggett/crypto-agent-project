.PHONY: test test-unit smoke

test:
	python -m pytest

test-unit:
	python -m pytest tests/unit

smoke:
	python -m pytest tests/unit/test_repo_skeleton_imports.py
