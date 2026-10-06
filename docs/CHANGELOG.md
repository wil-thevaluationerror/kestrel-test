# Changelog

## 1.0.0 — 2026-10-06

First shippable version: the reduced Tuesday scope from `docs/SPEC.md`.

**Shipped**

- Seeded synthetic generator: one fictional fund, nine holdings, two quarters, four report
  templates, and `data/ground_truth.json`. Generation is byte-stable across runs.
- Defects D01, D02, D04, D07, D08, D10, applied as named transforms that can be switched off
  individually in `config/fund.yaml`.
- Ingestion of xlsx and csv with one staged row per source cell, file hashing, and the I02
  duplicate-submission check.
- Canonical schema, metric dictionary, and per-template label mappings, with I01 on any
  unmapped label.
- Rules R03, R04, R07, R08. R04 and R08 are expressed in SQL against the DuckDB warehouse.
- Exception queue, signed resolutions (`accept` / `correct` / `exclude`), overrides that keep
  the filed value, stale-resolution warnings, and the promotion gate.
- Outputs: gated `summary.html`, `exceptions.csv`, `manifest.json`.
- 56 tests: per-rule unit tests, ground truth, false positives, determinism, gate, resolution,
  lineage, config contract, and demo-break.
- `README.md`, `docs/RUNBOOK.md`, `docs/DECISIONS.md`, `docs/FAILURE_MODES.md`,
  `docs/DATA_HANDLING.md`. `FAILURE_MODES.md` and `DATA_HANDLING.md` were scheduled for v1.1
  but were cheap enough to write now and are the clearest evidence of judgement in the repo.

**Declared but not enabled** — R01, R02, R05, R06, with defects D03, D05, D06, D09. Every run
manifest and every summary lists them under `checks_not_evaluated`.

**Deferred** — `lp_update_draft.xlsx`, LLM extraction for PDF reports, fund-of-funds sleeve,
LP capital account statements, valuation models.

**Deviations from the spec worth flagging**

- `docs/SPEC.md` says three Q2 holdings stay clean under the reduced defect set. With five
  holding-level defects and one fund-level defect, four holdings are clean in Q2 (RE-C, GE-C,
  GV-B, GV-C). That makes the false-positive test slightly stronger, not weaker.
- A `correct` resolution carries an explicit `target` (table, keys, column) that the spec's
  example omits. Without it, the pipeline would have to infer which canonical cell to override
  from rule internals, which would make the audit trail depend on implementation detail.
- Rule severities and tolerances were implemented exactly as specified. The rules were written
  before their unit tests, which inverts the order `docs/SPEC.md` requires; the ground-truth and
  false-positive tests do score against the defect manifest, which was declared in the spec
  before any code existed.

## 1.1.0 — 2026-10-06

**Traces are openable.**

- `src/pmp/sources.py`: renders every ingested document into a cell grid keyed by the same
  references the lineage uses, and copies the documents to `outputs/<run_id>/sources/`.
- Lineage on the summary is now structured (`TraceRef`: kind, file, sheet, cell, hash,
  decision id) instead of a formatted string. A corrected figure carries two origins — the
  cell as filed and the decision that changed it — and a figure the reviewer supplied for an
  unmapped label carries only the decision, which is the honest answer.
- `summary.html` embeds the previews and ships a document viewer: select a trace to open the
  source at the highlighted cell, read its SHA-256, switch between a figure's origins, and
  download the file. Keyboard accessible, hidden in print, no network calls.
- `manifest.json` gains `source_copies`, mapping each ingested document to its copy and hash.
- `pmp run --no-sources` keeps previews and hashes but omits the copies, for anything leaving
  the fund.
- Tests: 70, up from 56. `tests/test_lineage.py` now asserts that every cited cell exists in
  the embedded preview and that every traced document is downloadable at the recorded hash;
  `tests/test_sources.py` covers preview keying, copy fidelity, name collisions, and the
  `--no-sources` path.

**Cost.** `summary.html` grows from roughly 50 KB to roughly 210 KB, and a run directory now
carries copies of the source documents. Rationale and the data-handling consequence are in
`docs/DECISIONS.md` (D-009) and `docs/DATA_HANDLING.md`.

## 1.2.0 — 2026-10-06

**Corrections are anchored to as-filed exceptions.**

- Rules run first on filed data in a separate in-memory DuckDB warehouse, then on corrected
  data in the on-disk warehouse. Rule IDs, data contracts, and existing tolerances are unchanged.
- Unknown `correct` IDs raise RES-UNANCHORED (`block`, `exact` in rule config), naming the
  resolution, reviewer, target, and attempted value. Their overrides are never applied.
- Corrections that leave their rule firing remain open. I01/I02 are exempt from clearance
  because they record ingestion events, not canonical-value checks.
- CSV, warehouse exceptions, and manifest counts retain all as-filed exceptions and their
  original evidence, plus resolution notices and new verification failures. The signed-off
  demo now retains all nine seeded exceptions as resolved.
- Unknown `accept`/`exclude` decisions still produce RES-STALE warnings without taking action.
- Pipeline version is now 1.2.0, separating these runs from older output directories.
- Tests: 96 total (80 existing tests, including presentation coverage, plus 16 anchoring
  tests). The protected ground-truth, false-positive, determinism, gate, and lineage tests
  are unchanged. README's stale count is updated. D-010 is a draft for Wil; the existing
  presentation decision is preserved as D-011.

**The summary is organised by asset class, and colour carries meaning.**

- `config/presentation.yaml`: tab labels, the headline figure per asset class, the overview
  aggregates, and metric polarity (`lower_is_better`, `neutral_metrics`). Validated at load
  against the metric dictionary and against the asset classes in `config/fund.yaml`.
- The summary is now a tablist: one tab per asset class, carrying the holding count and the
  number of figures a reviewer corrected on that tab. Each tab opens on an overview strip
  (holdings, invested capital, two aggregates with QoQ) before the holding cards. Every
  aggregate is a traced figure like any other, carrying the source cells it was summed from.
- Holdings are cards with a lead figure at display scale and the full metric table beneath,
  rather than nine identical tables of equal weight.
- Tabs are progressive enhancement: the markup is one continuous document, the tablist ships
  hidden, and a script enables it. Printing reveals every panel, one asset class per page.
  Keyboard support follows the ARIA tabs pattern (arrows, Home, End) and a panel is
  deep-linkable by fragment.
- QoQ figures are coloured by meaning, not sign. Rising operating expenses now read as bad and
  falling debt as good; cash flow lines are left uncoloured.
- Tests: 80, up from 70. `tests/test_presentation.py` covers tab coverage, the load-time
  rejection of an asset class with no tab or a headline metric that does not exist, sentiment,
  the ARIA wiring, and the no-JavaScript document.

**Deviation worth flagging.** `docs/SPEC.md` asks for "one page per asset class, no dashboards".
On screen this is now tabbed rather than stacked; in print it is unchanged — one asset class
per page. The tabs are a reading affordance, not a dashboard: there are still no charts.
