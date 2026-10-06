Portfolio Monitoring Pipeline — Build Spec & Agent Handoff
Oct 5, 2026 · @Wil
Purpose and context
Build a small, reproducible pipeline that ingests messy quarterly portfolio reports for a fictional multi-asset fund, catches data problems before they reach a report, and produces an auditable fund summary. Ship Tuesday, Oct 6, 2026, using the reduced scope below.
This is a work sample for an Investment Operations Associate role at a multi-asset Ohio fund (real estate and infrastructure, growth equity, growth venture). Reviewers are fund partners with about five minutes. They will watch a 3–4 minute walkthrough and skim a one-page memo; very few will open the code.
The sample must prove three things:
• Operations judgment. I know which steps to automate (collection, mapping, validation, reconciliation, drafting) and which stay human (valuation marks, exception sign-off, anything LP-facing).
• Controls. Every reported number traces to a source file, and bad data blocks the report instead of flowing through silently.
• Maintainability. Tests, a runbook, and a decisions log show the system can be kept working when inputs change.
It is not a product, a startup, or a demo of AI capability. Breadth is a failure mode here.
Principles and non-negotiables
Every agent working on this repo follows these rules. If a request conflicts with one, stop and flag it.
1. Synthetic data only. No real fund, LP, or portfolio-company data, and no data from any prior employer, even anonymized. The fictional fund and holdings must not resemble the real fund.
2. Deterministic core. Same inputs and seed produce byte-identical outputs. No network calls and no LLM anywhere in the v1 pipeline.
3. Nothing fails silently. An unmapped label, a missing period, or a failed rule becomes a logged exception. Never drop, coerce, or default a value without recording it.
4. Raw inputs are immutable. Files in data/raw/ are never edited by code. Corrections happen through a recorded resolution, not by changing source.
5. Lineage on every number. Each canonical value carries its source file, sheet, row or cell reference, file hash, and run ID.
6. Gate before output. Any open blocking exception prevents the fund report from being generated.
7. Falsify first. Write the test for a rule before the rule. The pipeline is only trusted if it catches every injected defect and flags nothing on clean holdings.
8. Simple over clever. Small functions, plain Python, the dependency list below and nothing else. No web app, no database server, no orchestration framework.
9. Wil must be able to explain every line. If a design choice can't be explained in two sentences, simplify it.
Scope
v1 is a command-line pipeline over one fictional fund, nine holdings, and two quarters. Anything not listed under "In" is out until v1 ships.
Bucket
Items
In
Seeded synthetic data generator with a ground-truth defect manifest; ingestion of xlsx and csv reports; mapping to a canonical schema; validation and reconciliation rules; exception queue; human resolution file; promotion gate; HTML fund summary; draft LP update table; run manifest; tests; maintenance docs
Out
Web UI, authentication, Postgres, Docker, cloud deploy, real data, real integrations (fund admin, Carta, CRM), scheduling or orchestration
Deferred (documented, not built)
LLM extraction for PDF reports, behind confidence gates and human review; fund-of-funds sleeve; LP capital account statements; valuation models
The deferred list is part of the deliverable. A short "where I'd add AI, and how I'd gate it" note in the memo is a stronger signal than shipping it half-tested.
Tuesday cut. Shipping in about 24 hours means building the core that proves the point and moving the rest to v1.1. The gate, lineage, and ground-truth test are never cut.
Area
Ships Tuesday
Moves to v1.1
Defects
D01, D02, D04, D07, D08, D10
D03, D05, D06, D09
Checks
R03, R04, R07, R08, I01, I02
R01, R02, R05, R06
Outputs
summary.html, exceptions.csv, manifest.json
lp_update_draft.xlsx
Docs
README (with known limits and a data-handling section), DECISIONS.md with four entries in Wil's words, one-page RUNBOOK.md
Separate FAILURE_MODES.md and DATA_HANDLING.md; full runbook
Tests
Unit, ground-truth (six defects), false-positive, determinism, gate, resolution, lineage
make demo-break
Portfolio extras
Tally link only if its math is checked against Ohio guidance by Tuesday noon; VCIC model only if confirmed shareable
Anything not verified by then
With fewer defects, three Q2 holdings stay clean. That makes the false-positive test stronger, because clean and broken holdings sit in the same quarter.
Roles
One builder, one independent reviewer, one owner. Two agents never edit the same files.
Role
Who
Owns
Does not
Owner
Wil
Design decisions, the data contract, rule definitions and tolerances, DECISIONS.md entries, final review at every gate, the memo and walkthrough
Merge code he can't explain
Builder
Claude Code
Implementation in the repo, tests, docs drafts, one milestone at a time
Change the data contract, rules, or tolerances without Wil's approval; add dependencies; skip a gate
Reviewer
GPT
Red-team review: proposes defects the rules would miss, reviews diffs at each gate, critiques the memo for a partner audience
Write code into the repo
Why split it this way: a second model reviewing the first catches blind spots that self-review doesn't. Keeping GPT out of the code avoids two agents with different assumptions editing the same modules.
Architecture and data flow
The pipeline is eight stages in a straight run, with one gate and one human loop. Raw files are never edited; corrections enter only through resolutions.yaml, and the next run applies them with their own lineage.
Each stage is a separate module with one job, so a failure is easy to locate and each stage can be tested alone.
Stack and repo structure
Python 3.11+, DuckDB, Parquet, and seven libraries. Nothing else without Wil's approval.
Library
Used for
duckdb
Canonical tables and SQL-based checks
pandas
Reading and reshaping report files
openpyxl
Writing and reading xlsx reports
pydantic
Data contract models and config validation
pyyaml
Mappings, rule tolerances, resolutions
jinja2
Static HTML fund summary
pytest
All tests
Repo name: portfolio-monitoring-pipeline. Entry point is a Makefile so a reviewer runs one command.
portfolio-monitoring-pipeline/
  README.md            # what it is, how to run in 3 commands, what to look at
  Makefile             # make data | make run | make test | make demo-break
  config/
    fund.yaml          # fictional fund, holdings, asset classes
    mappings/          # one YAML per holding template: source label -> canonical metric
    rules.yaml         # rule IDs, severity, tolerances
    resolutions.yaml   # human decisions on exceptions (signed, dated)
  data/
    raw/               # generated reports, never edited by code
    staged/            # parsed Parquet, one file per source report
    warehouse.duckdb   # canonical tables
  src/pmp/
    generate.py        # seeded synthetic data + ground_truth.json
    ingest.py          # read raw files, hash, stage
    normalize.py       # apply mappings, attach lineage
    rules/             # one module per rule family
    exceptions.py      # build queue, apply resolutions, gate
    report.py          # HTML summary, LP draft, run manifest
    cli.py
  templates/           # jinja2
  outputs/<run_id>/    # summary.html, lp_update_draft.xlsx, exceptions.csv, manifest.json
  tests/
  docs/
    RUNBOOK.md  FAILURE_MODES.md  DECISIONS.md  CHANGELOG.md  DATA_HANDLING.md
Synthetic data universe and injected defects
The generator builds one fictional fund, nine holdings, and two quarters (Q1 and Q2 2026), then injects ten known defects. It also writes ground_truth.json listing every defect, so tests can check the pipeline catches all of them and nothing else.
Fund: "Lakeshore Partners Fund I" (fictional), about $250M commitments, 40 fictional LPs. Do not mirror any real fund's name, size, or holdings.
Holdings: three per asset class. Each has its own report template so ingestion faces real variety.
Asset class
Holdings
Report format
Core metrics
Real estate / infrastructure
3 properties
xlsx, one sheet per property
Revenue, opex, NOI, occupancy, debt balance
Growth equity
3 companies
xlsx, P&L plus cash bridge sheets
Revenue, gross profit, EBITDA, cash, debt
Growth venture
3 companies
csv for two, xlsx for one; monthly revenue
Revenue (monthly), burn, cash, cap table
Injected defects (the ground truth):
ID
Defect
Where
Should be caught by
D01
Cap table ownership sums to 97.4%
Venture holding A, Q2
R04
D02
"Total Revenue" renamed "Net Sales"
Growth equity holding B, Q2
Unmapped label exception
D03
One month of revenue missing
Venture holding B, Q2
R02
D04
Cash bridge off by $48,200
Growth equity holding A, Q2
R03
D05
Revenue up 62% QoQ with no commentary
Growth equity holding C, Q2
R06
D06
Q2 file carries Q1 period dates
Venture holding C, Q2
R01
D07
Same file submitted twice
Real estate property A, Q2
Duplicate hash check
D08
Reported in thousands, not dollars
Real estate property B, Q2
R07
D09
Occupancy 104% and NOI ≠ revenue − opex
Real estate property C, Q2
R05
D10
Sum of LP called capital ≠ fund called capital
Fund level, Q2
R08
Q1 is clean for every holding. In Q2 each holding carries exactly one defect. The false-positive test asserts that Q1 produces zero exceptions and that each Q2 holding produces exceptions only for its own defect.
Generation rules: one fixed seed in fund.yaml; numbers plausible for each asset class; all values in USD; defects applied as named, logged transforms after clean data is built, so turning off a defect regenerates the clean file exactly.
Data contract
The data contract is the most important design artifact in the repo. Wil approves it before any ingestion code is written, and changes to it need a DECISIONS.md entry.
Canonical tables (DuckDB):
Table
Grain
Key columns
holdings
One row per holding
holding_id, name, asset_class, invested_capital_usd, entry_date
metrics
One row per holding, period, metric
holding_id, period_end, metric, value, unit, frequency, lineage fields
cap_table
One row per holding, period, share class or holder
holding_id, period_end, holder, shares, ownership_pct, lineage fields
lp_capital
One row per LP, period
lp_id, period_end, commitment_usd, called_usd, distributed_usd
fund_summary
One row per period
period_end, total_commitments_usd, total_called_usd
exceptions
One row per rule failure
exception_id, rule_id, severity, holding_id, period_end, evidence, status
Lineage fields on every source-derived row: source_file, source_sheet, source_ref (cell or row), file_sha256, run_id, mapping_version.
Metric dictionary: a fixed list of canonical metric names per asset class, with unit and expected frequency. For example, revenue (USD, monthly for venture, quarterly otherwise), noi (USD, quarterly), occupancy_pct (percent, quarterly), cash_end (USD, quarterly).
Mapping config: one YAML file per holding template. Each maps a source label to a canonical metric and declares the unit scale (dollars or thousands). Rules for mapping:
• An unmapped source label creates an exception. It is never ignored.
• A canonical metric expected for that asset class but missing from the file creates an exception.
• A unit scale change must be declared in the mapping. Undeclared scale changes are what R07 exists to catch.
Validation and reconciliation rules
Eight rules plus two ingestion checks. Each rule is a small pure function that takes canonical data and returns exceptions with evidence. Severity and tolerances live in rules.yaml, not in code.
ID
Rule
Logic
Severity
Tolerance
R01
Period integrity
Dates in the file match the reporting period it was submitted for
Block
Exact
R02
Completeness
Every expected metric and month is present for the period
Block
None missing
R03
Cash bridge ties
Beginning cash + flows = ending cash
Block
±$1
R04
Cap table sums
Ownership across holders sums to 100%
Block
±0.01%
R05
Real estate internal consistency
NOI = revenue − opex; occupancy between 0% and 100%
Block
±$1; hard bounds
R06
QoQ variance
Revenue or cash change above threshold needs commentary in the resolution file
Warn
35%
R07
Unit scale anomaly
A metric changes by roughly 1,000× QoQ with no declared scale change
Block
Ratio between 500 and 2,000
R08
LP reconciliation
Sum of LP called capital = fund called capital
Block
±$1
I01
Unmapped label
Source label has no mapping entry
Block
—
I02
Duplicate submission
File hash already ingested for that holding and period
Block
Exact hash
Every exception records the rule ID, holding, period, the values compared, the difference, and the lineage of each value involved. A reviewer should understand the problem from the exception row alone, without opening the source file.
Warn means the report can still run, but the warning appears in the summary until a reviewer adds commentary. Block means the gate holds the report until a resolution exists.
Exceptions queue and human review gate
The gate is the point of the project. Automation finds and explains problems; a named person decides what happens to them.
1. A run writes all exceptions to outputs/<run_id>/exceptions.csv and the exceptions table, each with status open.
2. A reviewer adds an entry to config/resolutions.yaml for each exception: reviewer name, date, decision, and rationale.
3. Allowed decisions: accept (data is right, rule fired correctly but the case is legitimate, e.g. a real revenue spike), correct (supply the corrected value and its source, which is applied as an override with its own lineage), or exclude (hold this holding out of the report for the period, with reason).
4. The next run applies resolutions. An override never edits the raw file; it is stored as a separate record that points at the original value.
5. The gate checks for any open Block exception. If one exists, the report step stops and prints which exceptions are holding it.
6. The summary report lists every resolution applied that period, so nothing is fixed invisibly.
Example resolution entry:
- exception_id: EX-2026Q2-GE-A-R03
  decision: correct
  corrected_value: 4182300
  source: "Email from company CFO, revised cash bridge v2"
  reviewer: W. Butler-Croutwater
  date: 2026-10-07
  rationale: "Company omitted a $48.2K equipment payment from the bridge."
Outputs and audit trail
Four files per run, all under outputs/<run_id>/. The HTML summary is what appears in the walkthrough.
File
Contents
Audience
summary.html
Fund-level quarter view by asset class; per-holding key metrics with QoQ change; open warnings; resolutions applied this period; a "trace" link or tooltip on each number showing file, sheet, cell, and hash
Partners, investment team
lp_update_draft.xlsx
Portfolio table for an LP letter, watermarked DRAFT, with a reviewer sign-off cell left blank
Ops, IR
exceptions.csv
Every exception raised, its status, and resolution
Ops reviewer
manifest.json
run_id, timestamp, git commit, input file hashes, mapping and rule config hashes, counts by rule and severity, gate result
Audit trail
Design the summary for print and plain reading: one page per asset class, no dashboards, no charts beyond one QoQ table per class. It should look like something a fund would actually send around internally.
Testing and acceptance
v1 is done when every check below passes from a fresh clone with make data && make test && make run.
[ ] Unit tests per rule: at least one passing case and one failing case each, written before the rule.
[ ] Ground-truth test: all ten defects in ground_truth.json are detected by the expected rule. Recall 100%.
[ ] False-positive test: Q1 produces zero exceptions; each Q2 holding produces exceptions only for its own defect. Precision 100% on the synthetic set.
[ ] Determinism test: two runs on the same inputs produce identical manifest.json input hashes and identical canonical table contents.
[ ] Gate test: with any open Block exception, make run refuses to build the report and names the blocking exceptions.
[ ] Resolution test: after resolutions are added, the report builds and lists every resolution applied.
[ ] Lineage test: every number in the summary traces back to a raw file cell or a resolution record.
[ ] Demo-break: make demo-break changes one template label in a copy of the raw data and shows the pipeline raising I01 instead of producing a wrong report.
100% on synthetic data proves the rules work as designed. It does not prove they catch everything in real data. Say that plainly in the README.
Maintenance documentation
These docs are the evidence for "can maintain it." Claude Code drafts them; Wil rewrites DECISIONS.md in his own words.
Doc
Contents
README.md
What it is in three sentences, how to run it, what to look at first, known limits
RUNBOOK.md
Procedures: onboarding a new holding, handling a changed template, changing a tolerance, rerunning a quarter, resolving each exception type
FAILURE_MODES.md
What can go wrong (bad mapping, stale resolution, duplicate file, silent unit change, rule too loose), how each is detected, and what isn't detected yet
DECISIONS.md
Short entries: decision, alternatives considered, why. At least six, e.g. why DuckDB over Postgres, why YAML resolutions over a UI, why no LLM in v1, why Block vs Warn for each rule
CHANGELOG.md
Dated changes by version
DATA_HANDLING.md
See the next section
Security and data handling
DATA_HANDLING.md is half a page on how this design would treat real LP and portfolio data. It is written as a position, not a compliance claim.
• What data this would touch: portfolio company financials, cap tables, LP identities and capital accounts. All confidential; LP data most sensitive.
• Where it lives: inside the fund's own environment. No copies on personal machines; outputs stored with the same access as the source.
• Third-party AI: no confidential data sent to an external model without the fund's approval and a contract covering retention and training. The deferred LLM extraction step would run only under those terms, or against a locally hosted model.
• Access: least privilege; raw files read-only; resolutions require a named reviewer, so every change has an owner.
• Integrity: file hashes, immutable raw data, and the run manifest make tampering or accidental edits detectable.
• This repo: synthetic data only, no secrets, no network calls. State this in the README's first lines.
Milestones
Two working sessions, tonight and Tuesday, with a send target of 5 p.m. Tuesday. Nothing moves forward until Wil passes the gate himself.
If a session slips, cut scope instead of the date: drop the RUNBOOK, then R07 and D08. Fallback rule: if Gate 1 isn't passed by 2 p.m. Tuesday, send Wednesday morning. A late sample costs a day; a broken gate in front of a partner costs the point of the project.
Agent prompts
Paste these at the start of each session. Point both agents at this document as the source of truth.
Claude Code — session opener (save as CLAUDE.md in the repo root):
You are the builder for portfolio-monitoring-pipeline. The spec in docs/SPEC.md is the source of truth.

Rules:
- Work on one milestone at a time. Stop at the end of each milestone and summarize: what you built, design choices made, and anything you were unsure about.
- Do not change the data contract, rule logic, severities, or tolerances. If you think one is wrong, say so and wait.
- Write the test for a rule before the rule.
- No dependencies beyond: duckdb, pandas, openpyxl, pydantic, pyyaml, jinja2, pytest.
- No network calls. No LLM calls. No real data.
- Never write code that edits files in data/raw/.
- Never drop, coerce, or default a value silently. Raise an exception record instead.
- Keep functions short with docstrings that say why, not just what.
- After each milestone, list 3 questions Wil should be able to answer about the code you wrote.
GPT — red-team reviewer prompt:
You are an independent reviewer for a portfolio monitoring pipeline built for an investment operations role at a multi-asset fund. You did not write this code. I will paste the spec and then a diff or file.

Your job:
1. Name data problems a real fund would hit that these rules would miss.
2. Find any place the code could fail silently, drop data, or let a bad number reach the report.
3. Flag anything I could not defend to a skeptical fund partner or CFO.
4. Do not rewrite the code. Give findings ranked by severity, each with the line or section it refers to.
GPT — memo reviewer prompt (use once at the end):
You are a partner at a multi-asset private investment fund reading a one-page memo from an Investment Operations Associate candidate. Tell me in under 150 words: what you'd remember, what you'd doubt, and what you'd ask in the next interview.
Wil's own checkpoint at every gate: answer Claude Code's three questions out loud without looking at the code, and write the DECISIONS.md entry yourself. If you can't, the milestone isn't done.
Open questions
[ ] What systems does the fund use today for portfolio monitoring and LP reporting (fund admin, Carta, Excel, CRM)? If known, rename inputs and outputs to match.
[ ] Is the VCIC capitalization model shareable under competition rules? Decides whether it ships as the third portfolio item.
[ ] Does the walkthrough include Tally, or does Tally stay a link in the memo?
[ ] Public GitHub repo, or private with access granted on request?