# Failure modes

What can go wrong, how it is detected, and what is not detected yet. The last column is the
important one.

## Detected

| Failure | Detected by | How the reviewer sees it |
|---|---|---|
| Source label renamed or added | I01, at parse time | Exception naming the label, file, sheet, and cell; the value is withheld and the gate holds |
| Same file submitted twice | I02, on file hash per holding and period | Exception naming both files and the shared hash; the second file's rows are never staged |
| Cash bridge does not tie | R03 | Exception showing all five components, the computed total, the filed total, and the difference |
| Cap table does not sum to 100% | R04 | Exception with the holder count, the sum, and the gap in percentage points |
| Template switched to thousands without telling anyone | R07, on a 500x–2,000x QoQ ratio with no declared scale change | Exception per affected metric, showing both quarters' values and the declared scale |
| LP capital does not tie to the fund total | R08 | Fund-level exception with the LP sum, the filed fund total, and the difference |
| Correction with no as-filed exception | RES-UNANCHORED (block) | Rejected resolution, reviewer, target, and attempted value are recorded; canonical data is unchanged and the gate holds |
| Correction that doesn't clear its exception | Verification rule pass after overrides | The original exception remains open and blocking, with its as-filed evidence retained; I01/I02 describe ingestion events and are exempt from clearance |
| A resolution no longer matches anything | RES-STALE (warn) | Warning on the summary naming the resolution and its reviewer |
| Filename outside the submission standard | `IngestError`, run stops | Error naming the file and the expected pattern |
| Non-numeric value in a cell mapped to a metric | `NormalizeError`, run stops | Error with the cell address and the offending text |
| Two files claiming the same canonical cell | `NormalizeError`, run stops | Error naming both source addresses |
| Raw file altered between runs | File hash in the manifest changes; the run id changes | Different run directory, different input hash |
| A tolerance quietly loosened | Config hash in the manifest changes | Different run id for the same inputs |
| A rule turned off | `rules_disabled` and `checks_not_evaluated` in the manifest and on the summary | "What this run did not check" section |
| A rule that could not be evaluated for a holding | `skipped` notes from the rule, surfaced the same way | Same section, naming the holding and what was missing |
| A source copy in the run pack that does not match the original | Hash recorded per copy in `manifest.json` under `source_copies` | Re-hash the download and compare; the summary shows the same hash next to the document |
| A holding whose asset class has no tab | Load-time check against `config/presentation.yaml` | Run stops naming the asset class; the holding cannot silently vanish from the summary |
| A headline or aggregate metric that does not exist | Load-time check against the metric dictionary | Run stops naming the metric and the asset class, instead of rendering a blank lead figure |
| A source file that became unreadable between ingestion and reporting | The run stops while building the source pack | Error naming the file; the file parsed once already, so a failure here is an integrity event |

## Not detected yet

Ranked by how much damage it would do on real data.

1. **A line item that silently disappears from a file.** R02 (completeness) is declared in
   `config/rules.yaml` but disabled. A metric that stops being reported produces no exception
   today; the summary simply shows "—" for that line. This is the single biggest gap and the
   first thing to build in v1.1.
2. **A file filed against the wrong period.** R01 (period integrity) is disabled. The
   submitted-for period comes from the filename, and the period dates inside the file are
   staged but not compared against it. A Q2 file carrying Q1 dates would be loaded as Q2.
3. **Internally inconsistent real estate figures.** R05 is disabled. NOI that does not equal
   revenue less opex, and occupancy above 100% or below 0%, are not caught.
4. **A large unexplained move.** R06 (QoQ variance) is disabled, so a 62% revenue jump with no
   commentary is not surfaced at all. Note that R07 only covers the specific 500x–2,000x band.
5. **A restatement filed alongside the original.** Two different files for the same holding and
   period with different contents are not caught by I02, which matches on identical bytes. If
   they produce overlapping canonical cells the run stops with a `NormalizeError`; if they
   produce disjoint cells (for instance a revised cap table only), both load and the later one
   is treated as additional data rather than a replacement. The procedure is to withdraw and
   resubmit, which is a control on the operator, not in the code.
6. **A wrong number that is internally consistent.** Every rule here is a consistency or
   reconciliation check. A company that reports revenue 10% too low in a bridge that ties, a
   cap table that sums to 100%, and the right units will pass every rule. Catching that needs
   an independent source — the administrator's statements, the audited accounts, or a
   year-over-year analytical review — not a tighter tolerance.
7. **A mapping that is confidently wrong.** If `config/mappings/*.yaml` maps "Total Revenue" to
   `gross_profit`, every run is silently wrong and nothing fires. The mapping is reviewed by a
   human and version-stamped on every canonical row, and that is the whole control.
8. **A stale resolution that still matches.** A reviewer decision from a prior quarter whose
   exception id happens to recur is reapplied without comment. Resolutions are scoped by
   exception id, which includes the period, so this requires the same problem in the same
   period — but there is no expiry date on a resolution.
9. **Collusion between a bad mapping and a bad file.** If a template switches to thousands and
   somebody adds a matching `scale_overrides` entry without written confirmation, R07 is
   silenced by design. The control is the written confirmation, documented in the runbook.
10. **A preview that disagrees with the file.** The preview shows the first 200 rows per sheet
    as the parser read them: no formulas, no formatting, no comments, no hidden rows beyond
    that limit. A figure driven by a formula shows its computed value, and anything a reviewer
    needs beyond that requires the download. The preview is an aid to checking lineage, not a
    substitute for the document.
11. **Anything outside xlsx and csv.** PDFs, emailed figures, and portal screenshots are not
    ingested at all. They would be keyed in by hand today, with no lineage beyond the operator.

## Known limits of the test evidence

The ground-truth test asserts 100% recall against six defects that were designed alongside the
rules, and the false-positive test asserts zero exceptions on the clean holdings in the same
quarter. That proves the plumbing works and that the rules are specific enough not to fire on
plausible clean data. It does not estimate how often these rules would fire correctly on real
submissions, because the synthetic generator writes exactly the files the parsers expect.
