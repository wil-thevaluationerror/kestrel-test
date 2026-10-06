# portfolio-monitoring-pipeline

**Synthetic data only.** The fund, its nine holdings, and its forty limited partners are
invented and resemble no real entity. No real fund, LP, or portfolio-company data is in this
repository, there are no secrets, and the pipeline makes no network calls and no LLM calls.

This is a command-line pipeline that ingests messy quarterly portfolio reports for a
fictional multi-asset fund, checks them against a declared set of validation and
reconciliation rules, and produces an auditable fund summary. Every reported number traces
back to a source file, sheet, and cell, or to a signed reviewer decision. Any unresolved
blocking exception stops the report from being produced at all.

## Run it

```sh
make data    # generate the synthetic reports and the defect manifest
make test    # 96 tests: rules, correction anchoring, ground truth, false positives, determinism, gate, lineage
make run     # ingest, check, gate - this run is expected to be HELD
```

`make run` exits non-zero and writes no summary, because the seeded data contains six
defects and none of them has been signed off. That is the pipeline working. To see the
other half of the loop:

```sh
make run-resolved   # the same run after a reviewer signed off every blocking exception
make demo-break     # rename one source label in a copy of the data; watch the gate hold
```

`make setup` is run for you by the other targets. Python 3.11+ is the only prerequisite.

## What to look at first

1. **`make run` output.** Nine blocking exceptions, each naming the holding, the values
   compared, the difference, and the tolerance it breached.
2. **`outputs/<run_id>/summary.html`** after `make run-resolved`. One tab per asset class,
   each opening on an overview of that sleeve and then a card per holding led by its
   headline figure. Tab labels carry the holding count and how many figures a reviewer
   corrected, so the problems are visible before you open anything. Select the `trace` marker
   next to any current-quarter figure: it opens the source document itself, scrolled to the
   cell behind the number and highlighted, with the file's SHA-256 and a button to download
   the file. A figure a reviewer corrected carries a second origin — the signed decision
   record — reachable from the same control or from its `override` marker. The notes section
   lists every reviewer decision applied this period, every open warning, and everything this
   run did not check.
3. **`outputs/<run_id>/sources/`**. A copy of every document the run ingested, which is what
   the download buttons point at. The manifest records each copy's hash, so the pack can be
   checked against the originals.
4. **`config/`.** The data contract (`metric_dictionary.yaml`), the label mappings, the rule
   tolerances, the signed resolutions, and `presentation.yaml` — which figure each asset class
   leads with and which direction counts as good. Nothing that a reviewer would want to argue
   with is buried in code.
5. **`outputs/<run_id>/manifest.json`.** Run id, git commit, every input hash, every config
   hash, exception counts, gate result, and the list of checks that were not evaluated.
6. **`docs/DECISIONS.md`** for why it is built this way, and **`docs/FAILURE_MODES.md`** for
   what it still does not catch.

## How it works

```
data/raw/            immutable source reports (xlsx, csv)
  -> ingest          hash, parse to one staged cell per row  -> data/staged/*.parquet
  -> normalize       map source labels to canonical metrics, attach lineage  (raises I01)
  -> resolutions     apply signed corrections as overrides that keep the filed value
  -> warehouse       canonical tables in data/warehouse.duckdb
  -> rules           R03 R04 R07 R08 + ingestion checks I01 I02
  -> queue           exceptions, statuses, reviewer decisions
  -> gate            any open blocking exception stops the next step
  -> outputs         summary.html (gated), exceptions.csv, manifest.json, sources/
```

The tabs are progressive enhancement: the page is rendered as one continuous document with
every asset class visible, and the script turns it into a tablist. With scripting off, or on
paper, every sleeve prints — one per page, as before.

The summary is self-contained: the document previews are embedded in the page, so a trace
still opens a year from now, from disk, with no server and no network. That costs about
200 KB of HTML. `make run --no-sources`, or `pmp run --no-sources`, keeps the previews but
skips copying the files — see the data-handling note below.

The human loop runs through `config/resolutions.yaml`: a reviewer adds a dated, signed
decision (`accept`, `correct`, or `exclude`) for each exception, and the next run applies it.
A correction is stored as an override that points at the value it replaced. Files in
`data/raw/` are never modified by any code in this repository.

## Known limits

- **100% recall and precision here means 100% on this synthetic set.** The rules catch every
  defect the generator injects, because the defects and the rules were designed together.
  That is a test of the plumbing, not evidence that the rules would catch everything a real
  fund sees. `docs/FAILURE_MODES.md` lists what is not detected.
- **Four rules are declared but not enabled.** R01 (period integrity), R02 (completeness),
  R05 (real estate internal consistency), and R06 (QoQ variance) are specified in
  `config/rules.yaml` with `enabled: false` and listed in every run manifest under
  `checks_not_evaluated`. Until R02 ships, a renamed line item is caught only by I01, and a
  silently dropped line item is not caught at all.
- **No PDF or email ingestion, and no LLM extraction.** Where an LLM would help, and how it
  would be gated, is written up in `docs/DECISIONS.md` rather than half-built.
- **One fund, two quarters, nine holdings.** No fund-of-funds sleeve, no LP capital account
  statements, no valuation models.
- **The document preview is a preview, not the file.** It shows the first 200 rows of each
  sheet as the parser read them, with no formulas, formatting, or comments. The download
  button is there because the preview is not a substitute for the original.
- **Valuation marks, exception sign-off, and anything LP-facing stay with a person.** This
  pipeline prepares and checks evidence; it does not decide anything.

## Data handling

See `docs/DATA_HANDLING.md` for how this design would treat real LP and portfolio-company
data. Short version: it would run inside the fund's environment, raw files stay read-only,
every change carries a named reviewer, and no confidential data goes to a third-party model
without the fund's approval and a contract covering retention and training.

One consequence of the trace feature is worth stating here: a run directory contains copies
of the portfolio companies' own reports. That is right for an internal evidence pack and
wrong for anything forwarded outside the fund, which is what `--no-sources` is for.
