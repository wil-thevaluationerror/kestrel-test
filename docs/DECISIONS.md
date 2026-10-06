# Decisions

> **Draft for Wil to rewrite in his own words.** Per `docs/SPEC.md`, the owner writes these
> entries; what follows is the builder's account of each choice so there is something concrete
> to agree or disagree with. If an entry cannot be defended in two sentences out loud, the
> design is wrong, not the wording.

Format: decision, alternatives considered, why.

---

## D-001 — DuckDB file over a Postgres server

**Decision.** Canonical tables live in a single `data/warehouse.duckdb` file, rebuilt from
scratch on every run.

**Alternatives.** Postgres in Docker; SQLite; pandas only, with no SQL layer.

**Why.** The reconciliation checks are set-based (sum ownership by holding, sum called capital
against a filed total) and read far better as SQL than as loops. DuckDB gives that with no
server to install, no credentials, and no state for a reviewer to get wrong — the whole
warehouse is one file they can delete. Postgres would add an operational surface that proves
nothing about the controls. Rebuilding rather than updating means a run is never a partial
mutation of a previous run.

---

## D-002 — Resolutions as a signed YAML file, not a review UI

**Decision.** The human loop is `config/resolutions.yaml`: one dated, signed entry per
exception, with a decision of `accept`, `correct`, or `exclude`.

**Alternatives.** A small web UI with a review queue; a spreadsheet; marking exceptions
resolved directly in the database.

**Why.** The decision record needs to be diffable, reviewable, and version controlled — who
decided what, when, and on what evidence. A YAML file in git gives all of that for free and
makes the sign-off itself a reviewable artifact. A UI would be the bigger part of the build
and would move the audit trail into a database where nobody can see its history. This is also
the honest answer about scale: at nine holdings a file is correct, and the decision to build a
UI should be driven by reviewer volume, not by it looking more finished.

---

## D-003 — No LLM anywhere in v1, and where one would go

**Decision.** The v1 pipeline is fully deterministic: no network calls, no model calls. Same
inputs and seed produce byte-identical outputs.

**Alternatives.** LLM extraction of PDF reports; an LLM pass to guess the canonical metric
behind an unmapped label; LLM-drafted exception commentary.

**Why.** Every control in this repo rests on reproducibility. A reviewer has to be able to run
it twice and get the same report, and an auditor has to be able to tie a number to a cell. A
model in the extraction path breaks both unless it is gated, and the gating is the hard part,
not the extraction.

Where a model would actually earn its place, in priority order:

1. **PDF and email extraction.** Property managers and smaller companies send PDFs. An
   extraction step would emit a candidate value *plus a page and bounding-box citation and a
   confidence score*, write it to a staging table rather than the canonical tables, and route
   anything below the confidence threshold — and a sample of everything above it — to human
   review. Canonical values would still carry the citation, so the lineage test still holds.
2. **Unmapped-label suggestion.** On an I01, propose the most likely canonical metric with a
   reason. It would be a suggestion inside the exception row, never an automatic mapping. The
   gate would still hold.
3. **Exception triage narrative.** Draft the plain-English description of what broke for the
   reviewer's queue. Lowest risk, because no number depends on it.

What would not change: the model never decides a value, never clears an exception, and never
touches `data/raw/`. Confidential data would only go to a model under the terms in
`docs/DATA_HANDLING.md`.

---

## D-004 — Block versus Warn, rule by rule

**Decision.** R03, R04, R07, R08, I01, and I02 are `block`. R06 (QoQ variance, deferred) is
`warn`. Stale resolutions are `warn`.

**Alternatives.** Everything blocks; everything warns; severity by asset class.

**Why.** The test is whether a wrong number could reach a report without anyone noticing. A
cash bridge that does not tie, a cap table that does not sum to 100%, an unmapped label, a
silent switch to thousands, LP capital that does not tie to the fund — each of those means a
specific figure in the summary is wrong or missing, so each one blocks. A large QoQ move, by
contrast, is usually real; it needs a reviewer's commentary next to it, not a stopped report.
That distinction matters operationally: if warnings blocked, reviewers would learn to clear
them without reading them, and the gate would become a formality.

---

## D-005 — Tolerances and severities in config, not in code

**Decision.** `config/rules.yaml` holds every rule's severity and tolerance; rule modules read
them. Changing a threshold is a config diff, and the config hash goes into the run manifest.

**Alternatives.** Constants in the rule modules; command-line flags.

**Why.** The tolerances are the part a fund partner or CFO would argue with, so they have to be
readable without reading Python, and a change to one has to be visible in the audit trail. The
manifest records the config hash, so two reports built with different tolerances are
distinguishable after the fact. `tests/test_config_contract.py` asserts that widening a
tolerance actually changes the outcome, so the config cannot quietly become decorative.

---

## D-006 — Corrections as overrides that keep the filed value; raw files immutable

**Decision.** `data/raw/` is read-only to all code. A `correct` decision writes an override
onto the canonical row, carrying `original_value`, `override_of` (the exception id), and the
source the reviewer cited. The summary marks every overridden figure.

**Alternatives.** Editing the source file; keeping a corrected copy of the raw file; storing
corrections in a separate table joined at report time.

**Why.** The filed number is evidence of what the company sent, and overwriting it destroys the
only record of the error. Keeping both means the summary can show "filed 414,737 → 462,937,
per the CFO's revised bridge" rather than just the right answer, which is the difference
between a corrected report and an auditable one. A joined table would work equally well; it is
simply more machinery than nine holdings need.

---

## D-007 — An unmapped label withholds the value rather than guessing it

**Decision.** On I01 the value does not enter the canonical tables at all, and the exception
blocks the report.

**Alternatives.** Fuzzy-matching the label to the nearest mapped metric; loading it as an
"unclassified" metric; skipping it with a log line.

**Why.** Fuzzy matching is how "Net Sales" quietly becomes revenue on a basis nobody checked.
Loading it unclassified means a number exists in the warehouse that no rule covers. A log line
is the thing this project exists to argue against. Withholding plus blocking is the only option
where the failure is impossible to miss, and it costs one reviewer decision per changed
template per quarter — which is the right amount of friction for a template change.

Consequence worth stating: until R02 (completeness) is enabled, a renamed label is caught by
I01 but a line item that simply disappears from a file is not caught at all. That is the first
thing to build in v1.1.

---

## D-008 — Deterministic run ids derived from input and config hashes

**Decision.** `run_id = "run-" + sha256(input hashes + config hashes + pipeline version)[:12]`.
The timestamp is injectable so determinism is testable.

**Alternatives.** Timestamp-based run ids; incrementing counters; UUIDs.

**Why.** The run id then answers the question a reviewer actually has — "which bytes and which
rules produced this report?" — without opening the manifest. It also makes rerunning a closed
quarter safe: identical inputs land in the same directory with identical contents, and any real
change produces a visibly different run. A timestamp id would create a new directory every run
and quietly allow two different reports to claim the same quarter.

---

## D-009 — Traces open the source document, and the run ships the documents

**Decision.** A trace marker is a control, not a tooltip. Selecting one opens the source
document, highlights the cell the figure came from, shows the file's SHA-256, and offers the
file for download. Every ingested document is copied to `outputs/<run_id>/sources/`, and each
copy's hash is recorded in the manifest. The document previews are embedded in `summary.html`
itself.

**Alternatives.** The hover tooltip it replaced; a plain file path for the reviewer to go and
find; a link straight to the file in `data/raw/`; a small server that renders source files on
request; a link out to the fund's document management system.

**Why.** A lineage string is a claim about where a number came from. A reviewer who wants to
check it still has to find the file, open it, and count down to the right row — which in
practice means they do not check it, and the control exists on paper only. Opening the
document at the cell turns the audit trail into something a partner can actually use in the
five minutes they have.

Embedding the previews rather than fetching them matters for the same reason the pipeline is
deterministic: the report has to keep working when it is filed, emailed, or opened from a
share a year from now. A server-rendered viewer would make the summary depend on the pipeline
still being deployed. Linking into `data/raw/` would break the moment the report moved, and
would make the report's correctness depend on files nobody promised not to reorganise.

Copying the documents costs roughly 200 KB of embedded HTML and the size of the source files
themselves, and it makes the run directory a self-contained evidence pack: the summary, the
exception register, the manifest, and every document behind them, each hash-checkable against
the original. The cost is that the pack carries the portfolio companies' own reports, which is
the right default internally and the wrong default for anything sent outside the fund. That is
what `--no-sources` is for, and why it degrades the download rather than the lineage: with the
pack off, every trace still opens its preview and still shows its hash.

**What this does not change.** `data/raw/` is still read-only to all code; the pack is copies.
The gate still decides whether a summary exists at all, and the source pack is built with the
summary rather than before it, because it exists to serve the summary.

---

## D-010 — Anchor corrections to as-filed exceptions (DRAFT for Wil to rewrite)

**Decision.** Run all enabled rules on as-filed canonical data, using a separate in-memory
DuckDB connection for SQL checks. Combine those failures with I01/I02 to define the only
exception IDs that can authorize a correction. Reject an unknown correction with
RES-UNANCHORED, whose blocking severity lives in `config/rules.yaml`. Apply anchored
corrections, build the corrected on-disk warehouse, and run the rules again to verify them.

**Alternatives considered.** Validating against only the corrected pass loses the very
exceptions a successful correction clears. Trusting an ID's format or the list of applied
overrides proves neither that a problem existed nor that it was fixed. Persisting a prior
run's register would require managing stale snapshots and binding them to input hashes.
Building both passes in the on-disk warehouse risks leaving filed values where reviewers
expect corrected values.

**Why.** Re-evaluating the same filed inputs gives each correction a reproducible anchor
without adding saved state. The second pass leaves unsuccessful corrections open and adds
any newly introduced failures. IDs use period, entity, rule, and metric identity, never
corrected values, so the same failure can be compared across passes. I01/I02 record what
arrived during ingestion and cannot disappear through a canonical correction; they are
exempt from the clearance check, while any rule failure introduced by their corrections
still blocks.

The register retains original evidence with resolution status, plus RES-* notices and new
verification failures. CSV, the warehouse exceptions table, and manifest counts all use
this same register. Overrides retain the attempted corrected values and original lineage,
including when verification holds the gate.

**Policy left unchanged.** Unknown `accept` and `exclude` IDs raise RES-STALE warnings and
take no action. Making these block would be a separate owner decision. Anchoring validates
an exception ID, not the semantic relationship between every target and that exception;
reviewers still need to check the target and source, especially for ingestion exceptions.

---

## D-011 — One tab per asset class, and colour that means something

**Decision.** The summary is organised as a tablist with one tab per asset class, each opening
on an overview of that sleeve and then a card per holding led by its headline figure. Tabs are
progressive enhancement: the page is rendered as one continuous document and a script turns it
into tabs, so printing and reading with scripting off are unchanged. `config/presentation.yaml`
decides the tab labels, the lead figure, the overview aggregates, and which direction of travel
reads as good.

**Alternatives.** The stacked tables it replaced; an accordion per holding; a sortable table of
all nine holdings; a filter control instead of tabs; hiding the detail tables behind a
disclosure on each card.

**Why.** Nine holdings across three sleeves is more than a reader can hold in their head, and
the previous page asked them to — identical four-column tables, same weight, no entry point.
A partner with five minutes could not tell where to look. Tabs match how the fund is actually
organised, and each tab now answers "how is this sleeve doing" before it shows the evidence.

The detail tables stay visible rather than collapsing behind a disclosure, because they are the
evidence the project exists to produce. The hierarchy comes from the lead figure, not from
hiding anything.

Two things are deliberately surfaced on the tab itself: the holding count, and how many figures
on that tab a reviewer corrected. A reader should be able to see that real estate carries four
restatements this quarter without opening it.

**Why colour needed fixing at the same time.** The page coloured any increase green and any
decrease red. That painted rising operating expenses as good news and falling debt as bad —
exactly backwards for two of the five real estate lines. Rather than hard-code a list of
"cost" metrics in the template, `presentation.yaml` declares `lower_is_better` per asset class
and `neutral_metrics` for lines that have no agreed direction. The cash flow lines are in that
second list on purpose: a large investing outflow can be a good quarter, and a summary that
claims otherwise is worse than one that stays quiet.

**Why presentation is config rather than code.** Which figure a sleeve leads with is the kind
of thing an investment team will want to change, and it is not a data contract decision — no
canonical value, rule, or tolerance is involved. Keeping it in `config/` means the change is a
reviewable diff, it is hashed into the run manifest like every other config file, and the
loader can reject a headline metric that does not exist instead of rendering a blank.
