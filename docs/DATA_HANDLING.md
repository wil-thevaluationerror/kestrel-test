# Data handling

This is a position on how the design would treat real data, not a compliance claim and not an
assertion that any of it has been audited.

**This repository.** Synthetic data only. No real fund, LP, or portfolio-company data, and
nothing from any prior employer, anonymized or otherwise. No secrets, no credentials, no
network calls, no model calls. The fund, holdings, and LPs are invented.

**What a real version would touch.** Portfolio-company financials and cap tables, property
operating statements, and LP identities and capital accounts. All of it confidential; the LP
capital data is the most sensitive, because it identifies named investors and their positions.

**Where it would live.** Inside the fund's own environment — its cloud tenant or its managed
devices — with the warehouse and outputs stored under the same access controls as the source
files. No copies on personal machines, and no source reports or outputs in a personal cloud
drive or a public repository. The generated synthetic set in this repo exists precisely so the
work sample can be public.

**Access.** Least privilege, by role. `data/raw/` read-only to the pipeline and to everyone
except the person who files submissions. Resolutions require a named reviewer and a date, so
every change to a reported figure has an owner you can go and ask. Outputs visible to the
investment team; LP-level capital detail restricted to the people who already see it.

**Third-party AI.** No confidential data to an external model without the fund's written
approval and a contract covering retention, training use, and subprocessors. The deferred PDF
extraction step would run either under those terms or against a model hosted inside the fund's
environment. Until one of those is true, the answer is that the step does not ship — which is
why there is no model in v1.

**The source pack.** Each run directory contains copies of every document it ingested, so a
reviewer can open and download the file behind any figure. On real data that means a run
directory holds the portfolio companies' own financials and the LP capital extract, not just
the summary. Two consequences. First, the run directory inherits the access controls of the
source files, not of the summary — it is not a thing to drop in a shared folder because it
looks like a report. Second, anything leaving the fund should be produced with
`--no-sources`, which keeps every trace and every hash but omits the copies. The default is
on because the common case is an internal pack that has to be auditable.

**Integrity.** SHA-256 on every input file, recorded in the run manifest with the config
hashes and the git commit. Raw files immutable, corrections stored as overrides that keep the
filed value. Accidental edits and tampering both show up as a changed input hash and a changed
run id.

**Retention and disposal.** Run directories are the audit record and would be retained on the
fund's schedule for financial records, not deleted when a quarter closes. Staged Parquet and
the warehouse are derived and can be rebuilt from raw at any time, so they are the first thing
to purge if storage is restricted.

**What I would not do.** Email source reports to myself to work on them, keep a "working copy"
of LP data outside the fund's environment, or paste a portfolio company's financials into a
chat window to speed up a reconciliation.
