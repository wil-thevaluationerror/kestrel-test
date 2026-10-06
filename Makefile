# Entry point for the whole project. A reviewer should never need to read this file.
PY := PYTHONPATH=src .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest

.PHONY: all setup data run run-resolved test demo-break clean

# `run` is deliberately excluded: on the seeded data it exits non-zero because the gate holds.
all: data test

.venv/bin/python:
	python3 -m venv .venv
	$(PIP) install --quiet --upgrade pip
	$(PIP) install --quiet -r requirements.txt

setup: .venv/bin/python
	@echo "environment ready"

# Generate the synthetic fund, its reports, and the defect manifest.
data: setup
	$(PY) -m pmp.cli data

# Full run against config/resolutions.yaml. Holds the gate while exceptions are unresolved.
# Exits non-zero when the gate holds, which on the seeded data is the expected result.
run: setup
	@$(PY) -m pmp.cli run || ( \
	  echo ""; \
	  echo "Non-zero exit because the gate held. On the seeded data that is the correct result."; \
	  echo "Next: make run-resolved   (the same quarter after a reviewer signed off)"; \
	  exit 1 )

# The same run after a reviewer has signed off every blocking exception.
run-resolved: setup
	$(PY) -m pmp.cli run --resolutions config/resolutions.demo.yaml

test: setup
	$(PYTEST) -q

# Rename a source label in a copy of the raw data and show the pipeline refuse to report.
demo-break: setup
	$(PY) -m pmp.cli demo-break

clean:
	rm -rf data/raw data/staged data/warehouse.duckdb data/ground_truth.json outputs .demo-break .pytest_cache
