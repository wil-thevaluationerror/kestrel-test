# Runbook

Operating procedures for the portfolio monitoring pipeline. One page; each procedure assumes
you are at the repo root with `make setup` already run.

## The normal quarterly cycle

1. Drop the quarter's submissions into `data/raw/<PERIOD>/<asset_class>/` using the naming
   standard below. Do not edit a file after it lands.
2. `make run`. Read the gate message.
3. For every blocking exception, add a decision to `config/resolutions.yaml` (see below).
4. `make run` again. When the gate passes, `outputs/<run_id>/summary.html` is the quarter's
   internal summary and `outputs/<run_id>/manifest.json` is the audit record.
5. File the whole `outputs/<run_id>/` directory, including `sources/`. The run id is derived
   from the input and config hashes, so it identifies exactly which bytes and which rules
   produced the report, and the directory holds a hash-checkable copy of every document the
   figures came from.

**Before sending a summary outside the fund**, rebuild it with `--no-sources`. Traces and
hashes still work; the copies of the portfolio companies' reports are omitted. See
`docs/DATA_HANDLING.md`.

**Checking a figure.** Select its `trace` marker. The source document opens at the cell, with
the file's SHA-256 and a download button. If the figure was corrected, a second chip opens the
signed decision behind it. Nothing on the page is reachable only by asking the person who
built the report.

## Submission naming standard

```
<HOLDING_ID>_<slug>_<PERIOD>[_<suffix>].<xlsx|csv>
```

Examples: `RE-A_harborview-logistics-park_2026Q2.xlsx`,
`GV-A_ridgeline-bio_2026Q2_cap-table.csv`,
`FUND_lakeshore-partners-fund-i_2026Q2_lp-capital.csv`.

Ingestion reads the holding and the submitted-for period from the filename. A file that does
not match is rejected with an error naming the file - it is never guessed at. Rename the file
to the standard rather than loosening the parser.

## Resolving an exception

Add one entry per exception to `config/resolutions.yaml`. One decision per exception id; a
second entry for the same id is rejected. The rationale must be a real sentence.

| Decision | Use when | Also required |
|---|---|---|
| `accept` | The rule fired correctly and the case is legitimate (a real revenue spike, a byte-identical duplicate that was already discarded). | `source` if there is one |
| `correct` | You have the right value from a named source. | `target` and `corrected_value` |
| `exclude` | The holding should be held out of this period's report. | nothing beyond the rationale |

A `correct` decision needs an explicit target so the audit trail does not depend on rule
internals:

```yaml
  - exception_id: EX-2026Q2-GE-A-R03
    decision: correct
    target:
      table: metrics            # metrics | cap_table | lp_capital | fund_summary
      keys: {holding_id: GE-A, period_label: 2026Q2, metric: cash_flow_investing, sub_period: 2026Q2}
      column: value
    corrected_value: -462937
    source: "Email from company CFO, revised cash bridge v2, 2026-10-06"
    reviewer: W. Butler-Croutwater
    date: 2026-10-06
    rationale: "Company omitted a $48.2K equipment payment from the investing line."
```

`config/resolutions.demo.yaml` is a worked example covering all six seeded defects.

Rules run on the as-filed data before any correction, then again on corrected data. The
register keeps all nine seeded exception IDs after demo sign-off, with `resolved:*` status
and the original evidence. A correction that leaves its rule exception firing stays open:
check the revised source and target, fix the supplied value, and rerun. I01 and I02 record
ingestion events, so canonical corrections cannot erase them; they are exempt from this
clearance check. The on-disk warehouse contains corrected values, even when the gate holds.

### By exception type

- **I01 unmapped label.** Confirm with the company which canonical metric the label is, then
  either (a) `correct` with a target on the `metrics` table to book the value for this quarter,
  and queue a mapping update for next quarter, or (b) `exclude` the holding if the label is
  genuinely new and nobody can say what it means yet. Do not add the label to the mapping and
  rerun the same quarter without recording the decision - that leaves no trace that the
  template changed.
- **I02 duplicate submission.** The second file was not loaded. `accept` with the retained
  file as the source. If the two files were meant to differ, the second is a restatement:
  withdraw the first submission and resubmit, rather than filing both.
- **R03 cash bridge.** Get a revised bridge from the company. `correct` the flow line that was
  wrong, not the ending cash balance - correcting the plug hides the error.
- **R04 cap table.** Check the share-count column in the same file; it usually corroborates the
  right percentage. `correct` the holder row that is wrong.
- **R07 unit scale.** Confirm the scale with the manager. If the change is permanent, `correct`
  this quarter's values and add a `scale_overrides` entry to the template mapping so next
  quarter maps cleanly (see below).
- **R08 LP reconciliation.** Reconcile against the administrator's capital account statements.
  `correct` the LP row, not the fund total, unless the administrator confirms the fund total is
  the wrong number.
- **RES-STALE (warn).** A resolution in the file no longer matches anything. Delete it once the
  quarter it belonged to is closed.
- **RES-UNANCHORED (block).** The correction's exact exception ID was never raised on the
  as-filed data, so its override was rejected. Read the row's reviewer, target, and attempted
  value, then compare its ID with the original exception register, including the period and
  metric suffix. For a transcription error, fix the ID only after confirming the source and
  target answer that real exception. If no matching exception exists, remove the unsupported
  correction and investigate the submission or missing control with the owner; do not invent
  an ID or borrow an unrelated exception. Rerun and confirm both resolution status and the
  gate. Adding an `accept` for the RES-UNANCHORED row does not authorize the rejected edit.

## Onboarding a new holding

1. Add the holding to `config/fund.yaml`: id, name, asset class, template, report format,
   invested capital, entry date.
2. If its asset class is new, add its canonical metrics to `config/metric_dictionary.yaml`
   with unit and expected frequency. This is a data contract change - write a
   `docs/DECISIONS.md` entry.
3. If its report template is new, add `config/mappings/<template>.yaml` mapping every source
   label to a canonical metric, and list the template's header and metadata labels under
   `ignore_labels`. Add a parser in `src/pmp/ingest.py` only if the shape is genuinely new.
4. `make run`. Any label you missed comes back as an I01 with its cell address.

## Handling a changed template

1. `make run` raises I01 for each changed label with the file, sheet, and cell.
2. Confirm with the company that the line means the same thing.
3. Resolve this quarter's exceptions as above so the quarter can close with a record of what
   happened.
4. Then update `config/mappings/<template>.yaml`: add the new label, bump `mapping_version`,
   and add a `docs/CHANGELOG.md` line. Leave the old label in place if both may appear.
5. Rerun. The run id changes because the config hash changed, which is intended: a new
   mapping produces a new, separately auditable run.

## Changing what the summary leads with

`config/presentation.yaml` decides, per asset class, the tab label, the figure each card leads
with, the aggregates in the tab overview, and which metrics read as good when they fall
(`lower_is_better`) or carry no judgement at all (`neutral_metrics`). It changes emphasis only;
no canonical value, rule, or tolerance is involved.

Every metric named there must exist in `config/metric_dictionary.yaml` for that asset class,
and every asset class used in `config/fund.yaml` must have an entry — otherwise the run stops
at load rather than quietly dropping a holding off the page.

## Changing a tolerance

Tolerances live in `config/rules.yaml` and nowhere else. Edit the value, run `make test`
(the rule unit tests assert behaviour at the tolerance boundary), and write a
`docs/DECISIONS.md` entry saying why the threshold moved. The config hash in the manifest
changes, so any report built before and after the change is distinguishable.

## Declaring a unit scale change

In the template mapping:

```yaml
scale_overrides: [{period: 2026Q3, scale: thousands}]
```

R07 then stops firing for that period's comparison. Only do this once the manager has
confirmed the change in writing - the whole point of R07 is that undeclared scale changes are
caught.

## Rerunning a closed quarter

Runs are idempotent: the same inputs and config produce the same run id and byte-identical
outputs, so rerunning overwrites a directory with identical contents. If the inputs or config
changed, the run id changes and the previous `outputs/<run_id>/` directory is left intact.
Never delete a filed run directory.

## When the pipeline stops with an error instead of an exception

Three conditions stop the run rather than producing an exception record, because the pipeline
cannot describe the data honestly:

- A filename outside the submission standard (`IngestError`).
- A non-numeric value in a cell mapped to a metric (`NormalizeError`, with the cell address).
- Two files claiming the same canonical cell (`NormalizeError`, naming both addresses).

Fix the submission, do not loosen the parser.
