"""Two rule passes anchor corrections and verify them before the reporting gate.

ingest -> normalize -> as-filed rules -> overrides -> warehouse -> verify -> queue -> gate

The exception register and the run manifest are always written, including when the gate
holds: a held run is a result that has to be auditable too. Only the fund summary is gated.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .configio import ConfigBundle, load_config
from .contract import ExceptionRow
from .exceptions import (
    AppliedOverride,
    GateResult,
    QueueOutcome,
    apply_overrides,
    build_queue,
    evaluate_gate,
)
from .hashing import sha256_json
from .ingest import DuplicateSubmission, StagedReport, ingest
from .normalize import Canonical, duplicate_exceptions, normalize
from .paths import Layout
from .report import (
    build_summary,
    git_commit,
    render_summary,
    write_exceptions_csv,
    write_manifest,
)
from .rules.base import RuleContext
from .rules.registry import run_rules
from .sources import SOURCES_DIRNAME, SourceBundle, collect
from .summary_model import Summary
from .textio import write_text
from .warehouse import build, stage_parquet, write_exceptions

PIPELINE_VERSION = "1.2.0"


@dataclass(frozen=True)
class RunResult:
    run_id: str
    outputs_dir: Path
    sources: SourceBundle
    canonical: Canonical
    queue: QueueOutcome
    gate: GateResult
    overrides: tuple[AppliedOverride, ...]
    summary: Summary | None
    manifest: dict
    written: tuple[Path, ...]


def compute_run_id(reports: list[StagedReport], config: ConfigBundle) -> str:
    """Derive the run id from the inputs and the config that interpret them.

    Deterministic on purpose: the same files plus the same rules produce the same run id, so
    re-running cannot quietly create a second version of the same quarter.
    """
    fingerprint = {
        "inputs": {str(r.path.name): r.file_sha256 for r in reports},
        "config": dict(config.config_hashes),
        "pipeline": PIPELINE_VERSION,
    }
    return "run-" + sha256_json(fingerprint)[:12]


def _holdings_frame(config: ConfigBundle) -> pd.DataFrame:
    return pd.DataFrame.from_records(
        [
            {
                "holding_id": h.holding_id,
                "name": h.name,
                "asset_class": h.asset_class,
                "invested_capital_usd": h.invested_capital_usd,
                "entry_date": h.entry_date,
            }
            for h in config.fund.holdings
        ]
    )


def _not_checked(config: ConfigBundle, disabled: tuple[str, ...], skipped: tuple[str, ...]) -> tuple[str, ...]:
    """Say out loud what was not evaluated. 'No exceptions' must never be read as 'all clear'."""
    lines = [
        f"{rule_id} ({config.rules.spec(rule_id).name}) is disabled in config/rules.yaml"
        for rule_id in disabled
    ]
    return tuple(lines + list(skipped))


def _counts(exceptions: tuple[ExceptionRow, ...]) -> dict:
    by_rule: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for exception in exceptions:
        by_rule[exception.rule_id] = by_rule.get(exception.rule_id, 0) + 1
        by_severity[exception.severity] = by_severity.get(exception.severity, 0) + 1
    return {
        "total": len(exceptions),
        "by_rule": dict(sorted(by_rule.items())),
        "by_severity": dict(sorted(by_severity.items())),
        "open": sum(1 for e in exceptions if e.status == "open"),
    }


def _manifest(
    *, run_id: str, generated_at: str, commit: str, reports: list[StagedReport],
    duplicates: list[DuplicateSubmission], config: ConfigBundle, rule_run,
    queue: QueueOutcome, gate: GateResult, overrides: tuple[AppliedOverride, ...],
    not_checked: tuple[str, ...], outputs: list[str], period_label: str,
    sources: SourceBundle,
) -> dict:
    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "git_commit": commit,
        "pipeline_version": PIPELINE_VERSION,
        "reporting_period": period_label,
        "inputs": {r.holding_id + "/" + r.path.name: r.file_sha256 for r in reports},
        "input_count": len(reports),
        "duplicate_submissions": [
            {"file": d.path.name, "holding_id": d.holding_id, "period": d.period_label,
             "sha256": d.file_sha256, "identical_to": d.first_seen}
            for d in duplicates
        ],
        "config_hashes": dict(config.config_hashes),
        "rules_run": list(rule_run.rules_run),
        "rules_disabled": list(rule_run.rules_disabled),
        "checks_not_evaluated": list(not_checked),
        "exception_counts": _counts(queue.exceptions),
        "gate": {
            "passed": gate.passed,
            "blocking_exception_ids": [e.exception_id for e in gate.blocking],
        },
        "resolutions_applied": [
            {"exception_id": r.exception_id, "decision": r.decision, "reviewer": r.reviewer,
             "date": r.date, "rationale": r.rationale}
            for r in queue.resolutions_applied
        ],
        "overrides_applied": [asdict(o) for o in overrides],
        "outputs": sorted(outputs),
        "source_copies": {
            path: {"download": document.download, "sha256": document.sha256}
            for path, document in sorted(sources.documents.items())
            if document.download
        },
    }


def run(
    layout: Layout,
    *,
    resolutions_path: Path | None = None,
    period_label: str | None = None,
    generated_at: str | None = None,
    copy_sources: bool = True,
) -> RunResult:
    """Execute one full run. `generated_at` is injectable so determinism can be tested.

    `copy_sources` controls whether the ingested documents are copied next to the report. On
    by default: a trace a reviewer cannot open is only a claim. See docs/DATA_HANDLING.md for
    when to turn it off.
    """
    config = load_config(layout, resolutions_path=resolutions_path)
    reports, duplicates = ingest(layout, config.fund)
    if not reports:
        raise RuntimeError(f"no source reports found under {layout.raw} - run `make data` first")

    run_id = compute_run_id(reports, config)
    timestamp = generated_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
    commit = git_commit(layout)

    canonical, ingestion_exceptions = normalize(reports, config, run_id)
    ingestion_exceptions += duplicate_exceptions(duplicates, config)
    stage_parquet(reports, layout)

    # SQL rules must see filed values without putting them in the corrected warehouse.
    holdings = _holdings_frame(config)
    filed_connection = build(canonical, holdings, path=None)
    try:
        filed_rules = run_rules(RuleContext(canonical=canonical, config=config, connection=filed_connection))
    finally:
        filed_connection.close()
    as_filed = list(ingestion_exceptions) + list(filed_rules.exceptions)
    anchored_ids = frozenset(e.exception_id for e in as_filed)

    overrides = apply_overrides(canonical, config, run_id, anchored_ids)
    canonical = overrides.canonical

    connection = build(canonical, holdings, layout.warehouse)
    try:
        rule_run = run_rules(RuleContext(canonical=canonical, config=config, connection=connection))
        queue = build_queue(as_filed, config, overrides, rule_run.exceptions)
        write_exceptions(connection, list(queue.exceptions))
    finally:
        connection.close()

    gate = evaluate_gate(queue)
    periods = [p.label for p in config.fund.periods]
    reporting_period = period_label or periods[-1]
    prior_period = periods[periods.index(reporting_period) - 1] if periods.index(reporting_period) else reporting_period

    outputs_dir = layout.outputs(run_id)
    outputs_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = [
        write_exceptions_csv(queue.exceptions, outputs_dir / "exceptions.csv")
    ]

    not_checked = _not_checked(config, rule_run.rules_disabled, rule_run.skipped)
    summary: Summary | None = None
    sources = SourceBundle()
    if gate.passed:
        # Source documents are gathered with the summary because they exist to serve it.
        sources = collect(
            paths=[r.path for r in reports]
            + [d.path for d in duplicates]
            + [layout.config / "fund.yaml", layout.root / config.resolutions_file],
            repo_root=layout.root,
            outputs_dir=outputs_dir,
            copy_files=copy_sources,
        )
        summary = build_summary(
            canonical=canonical, config=config, queue=queue, overrides=overrides.applied,
            gate=gate, run_id=run_id, generated_at=timestamp, commit=commit,
            not_checked=not_checked, period_label=reporting_period, prior_label=prior_period,
            sources=sources,
        )
        write_text(outputs_dir / "summary.html", render_summary(summary, layout))
        written.append(outputs_dir / "summary.html")

    manifest = _manifest(
        run_id=run_id, generated_at=timestamp, commit=commit, reports=reports,
        duplicates=duplicates, config=config, rule_run=rule_run, queue=queue, gate=gate,
        overrides=overrides.applied, not_checked=not_checked, period_label=reporting_period,
        outputs=[p.name for p in written] + ["manifest.json"]
        + ([f"{SOURCES_DIRNAME}/"] if sources.documents and copy_sources else []),
        sources=sources,
    )
    written.append(write_manifest(manifest, outputs_dir / "manifest.json"))

    return RunResult(
        run_id=run_id, outputs_dir=outputs_dir, sources=sources,
        canonical=canonical, queue=queue, gate=gate,
        overrides=overrides.applied, summary=summary, manifest=manifest,
        written=tuple(written),
    )
