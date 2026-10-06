# portfolio-monitoring-pipeline — builder instructions

You are the builder for this repository. The spec in `docs/SPEC.md` is the source of truth.

Rules:

- Work on one milestone at a time. Stop at the end of each milestone and summarize: what you
  built, design choices made, and anything you were unsure about.
- Do not change the data contract, rule logic, severities, or tolerances. If you think one is
  wrong, say so and wait.
- Write the test for a rule before the rule.
- No dependencies beyond: duckdb, pandas, openpyxl, pydantic, pyyaml, jinja2, pytest.
- No network calls. No LLM calls. No real data.
- Never write code that edits files in `data/raw/`.
- Never drop, coerce, or default a value silently. Raise an exception record instead.
- Keep functions short with docstrings that say why, not just what.
- After each milestone, list 3 questions Wil should be able to answer about the code you wrote.

Repo conventions:

- Thresholds, severities, mappings, and reviewer decisions live in `config/*.yaml`, never in
  code.
- Every canonical value carries lineage: source file, sheet, cell, file hash, run id, mapping
  version.
- `make test` must stay green. The ground-truth, false-positive, determinism, gate, and lineage
  tests are the acceptance criteria and are not to be weakened to make a change pass.
