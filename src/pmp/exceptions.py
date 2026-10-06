"""The exception queue, the resolution loop, and the gate.

This module is the point of the project. Automation finds and explains problems; a named
person decides what happens to each one; nothing reaches the report until that has
happened. Raw files are never touched - a correction is stored as an override that points
back at the value it replaced.

Corrections are anchored. The rules run once on the data exactly as it was filed, and that
pass defines which exceptions exist. A `correct` resolution may only answer one of those: a
correction with no exception behind it is an unreviewed edit to a reported number, so it is
refused rather than applied. The rules then run a second time on the corrected data, and a
correction that did not actually clear the exception it answers leaves that exception open.
"""

from __future__ import annotations

from dataclasses import dataclass

from .configio import ConfigBundle
from .contract import (
    CapTableRow,
    ExceptionRow,
    FundSummaryRow,
    Lineage,
    LPCapitalRow,
    MetricRow,
    Resolution,
)
from .ids import exception_id
from .normalize import Canonical

TABLE_ROW_KEYS = {
    "metrics": ("holding_id", "period_label", "metric", "sub_period"),
    "cap_table": ("holding_id", "period_label", "holder"),
    "lp_capital": ("lp_id", "period_label"),
    "fund_summary": ("period_label",),
}
ALLOWED_OVERRIDE_COLUMNS = {
    "metrics": {"value"},
    "cap_table": {"ownership_pct", "shares"},
    "lp_capital": {"commitment_usd", "called_usd", "distributed_usd"},
    "fund_summary": {"total_commitments_usd", "total_called_usd"},
}


class ResolutionError(RuntimeError):
    """A resolution is malformed. Loud, because a misread sign-off is worse than none."""


@dataclass(frozen=True)
class AppliedOverride:
    exception_id: str
    table: str
    keys: dict[str, str]
    column: str
    original_value: float | None
    corrected_value: float
    reviewer: str
    source: str


METRIC_INSERT_KEYS = ("holding_id", "period_label", "metric", "sub_period")

# Raised during ingestion rather than by a rule reading canonical data, so re-running the
# rules can never make them stop firing. See _correction_cleared.
INGESTION_RULE_IDS = frozenset({"I01", "I02"})


@dataclass(frozen=True)
class OverrideOutcome:
    canonical: Canonical
    applied: tuple[AppliedOverride, ...]
    unmatched: tuple[Resolution, ...]
    unanchored: tuple[Resolution, ...] = ()


def _matches(row, keys: dict[str, str]) -> bool:
    """Match a canonical row against a resolution target by string comparison, so a YAML
    date and a python date do not silently fail to line up."""
    return all(str(getattr(row, name)) == str(value) for name, value in keys.items())


def _validate_target(resolution: Resolution) -> None:
    target = resolution.target
    if target is None or resolution.corrected_value is None:
        raise ResolutionError(
            f"{resolution.exception_id}: decision 'correct' needs both a target and a "
            "corrected_value"
        )
    if target.table not in TABLE_ROW_KEYS:
        raise ResolutionError(f"{resolution.exception_id}: unknown target table {target.table!r}")
    allowed_keys = set(TABLE_ROW_KEYS[target.table])
    unknown = set(target.keys) - allowed_keys
    if unknown:
        raise ResolutionError(
            f"{resolution.exception_id}: target keys {sorted(unknown)} are not key columns of "
            f"{target.table} (allowed: {sorted(allowed_keys)})"
        )
    if target.column not in ALLOWED_OVERRIDE_COLUMNS[target.table]:
        raise ResolutionError(
            f"{resolution.exception_id}: column {target.column!r} cannot be overridden on "
            f"{target.table}"
        )


def _override_rows(rows: tuple, resolution: Resolution) -> tuple[tuple, list[AppliedOverride]]:
    """Return the table with the override applied, plus a record of what changed."""
    target = resolution.target
    applied: list[AppliedOverride] = []
    updated = []
    for row in rows:
        if not _matches(row, target.keys):
            updated.append(row)
            continue
        original = float(getattr(row, target.column))
        lineage = row.lineage.model_copy(
            update={
                "override_of": resolution.exception_id,
                "override_source": resolution.source or resolution.rationale,
                "original_value": original,
            }
        )
        updated.append(
            row.model_copy(
                update={target.column: float(resolution.corrected_value), "lineage": lineage}
            )
        )
        applied.append(
            AppliedOverride(
                exception_id=resolution.exception_id,
                table=target.table,
                keys=dict(target.keys),
                column=target.column,
                original_value=original,
                corrected_value=float(resolution.corrected_value),
                reviewer=resolution.reviewer,
                source=resolution.source or "(rationale only)",
            )
        )
    return tuple(updated), applied


def _insert_metric(resolution: Resolution, config: ConfigBundle, run_id: str) -> MetricRow:
    """Book a value the reviewer supplied for a metric the file never provided in mappable form.

    This is the I01 path: the label was unrecognised, so no canonical row exists to update.
    The inserted row cites the resolution instead of a source cell, and carries no original
    value because there was none - which is exactly what the audit trail should say.
    """
    keys = resolution.target.keys
    missing = [k for k in METRIC_INSERT_KEYS if k not in keys]
    if missing:
        raise ResolutionError(
            f"{resolution.exception_id}: no canonical metric row matches this target, so the "
            f"value would be inserted - that needs all of {list(METRIC_INSERT_KEYS)} "
            f"(missing {missing})"
        )
    holding = config.fund.holding(keys["holding_id"])
    spec = config.dictionary.spec(holding.asset_class, keys["metric"])
    return MetricRow(
        holding_id=keys["holding_id"],
        period_end=config.fund.period(keys["period_label"]).period_end,
        period_label=keys["period_label"],
        metric=keys["metric"],
        value=float(resolution.corrected_value),
        unit=spec.unit,
        frequency=spec.frequency,
        sub_period=keys["sub_period"],
        lineage=Lineage(
            source_file=config.resolutions_file,
            source_sheet=None,
            source_ref=resolution.exception_id,
            file_sha256=config.resolutions_sha256,
            run_id=run_id,
            mapping_version="resolution",
            override_of=resolution.exception_id,
            override_source=resolution.source or resolution.rationale,
            original_value=None,
        ),
    )


def apply_overrides(
    canonical: Canonical, config: ConfigBundle, run_id: str, anchored_ids: frozenset[str]
) -> OverrideOutcome:
    """Apply the `correct` resolutions that answer an exception the as-filed data raised.

    `anchored_ids` is every exception id from the as-filed pass, ingestion checks included.
    A correction outside that set is not applied to anything: there is no recorded problem
    for it to be the answer to, so applying it would let a reviewer overwrite any reported
    number without a rule ever objecting. It comes back as RES-UNANCHORED instead.

    The override record keeps the filed value, so an applied change is never invisible.
    """
    tables = {
        "metrics": canonical.metrics,
        "cap_table": canonical.cap_table,
        "lp_capital": canonical.lp_capital,
        "fund_summary": canonical.fund_summary,
    }
    applied: list[AppliedOverride] = []
    unmatched: list[Resolution] = []
    unanchored: list[Resolution] = []

    for resolution in config.resolutions:
        if resolution.decision != "correct":
            continue
        _validate_target(resolution)
        if resolution.exception_id not in anchored_ids:
            unanchored.append(resolution)
            continue
        table = resolution.target.table
        tables[table], changes = _override_rows(tables[table], resolution)
        if not changes and table == "metrics":
            inserted = _insert_metric(resolution, config, run_id)
            tables["metrics"] = tables["metrics"] + (inserted,)
            changes = [
                AppliedOverride(
                    exception_id=resolution.exception_id,
                    table=table,
                    keys=dict(resolution.target.keys),
                    column=resolution.target.column,
                    original_value=None,
                    corrected_value=float(resolution.corrected_value),
                    reviewer=resolution.reviewer,
                    source=resolution.source or "(rationale only)",
                )
            ]
        elif not changes:
            unmatched.append(resolution)
        applied.extend(changes)

    return OverrideOutcome(
        canonical=Canonical(
            metrics=tables["metrics"],
            cap_table=tables["cap_table"],
            lp_capital=tables["lp_capital"],
            fund_summary=tables["fund_summary"],
        ),
        applied=tuple(applied),
        unmatched=tuple(unmatched),
        unanchored=tuple(unanchored),
    )


@dataclass(frozen=True)
class QueueOutcome:
    exceptions: tuple[ExceptionRow, ...]
    excluded: tuple[tuple[str, str], ...]  # (holding_id, period_label) held out of the report
    resolutions_applied: tuple[Resolution, ...]


def _stale_exception(resolution: Resolution, config: ConfigBundle, reason: str) -> ExceptionRow:
    severity = config.rules.spec("RES-STALE").severity
    return ExceptionRow(
        exception_id=exception_id("RES", resolution.exception_id, "RES-STALE"),
        rule_id="RES-STALE",
        severity=severity,
        holding_id="FUND",
        period_label="n/a",
        period_end=None,
        subject=resolution.exception_id,
        evidence=(
            f"Resolution for {resolution.exception_id} signed by {resolution.reviewer} "
            f"on {resolution.date} {reason}"
        ),
    )


def _unanchored_exception(resolution: Resolution, config: ConfigBundle) -> ExceptionRow:
    """Keep the rejected edit visible without applying it to any canonical row."""
    return ExceptionRow(
        exception_id=exception_id("RES", resolution.exception_id, "RES-UNANCHORED"),
        rule_id="RES-UNANCHORED",
        severity=config.rules.spec("RES-UNANCHORED").severity,
        holding_id=resolution.target.keys.get("holding_id", "FUND"),
        period_label=resolution.target.keys.get("period_label", "n/a"),
        period_end=None,
        subject=resolution.exception_id,
        evidence=(
            f"Resolution for {resolution.exception_id} signed by {resolution.reviewer} "
            f"on {resolution.date} attempted to set {resolution.target.table} "
            f"{dict(sorted(resolution.target.keys.items()))} column {resolution.target.column} "
            f"to {resolution.corrected_value}. No as-filed exception has this ID; "
            "the override was not applied."
        ),
        lineage_refs=(f"{config.resolutions_file}[{resolution.exception_id}]",),
    )


def _correction_cleared(exception: ExceptionRow, verification_ids: set[str]) -> bool:
    """I01/I02 describe ingestion events, so a canonical correction cannot erase them.

    They are exempt from clearance: the verification rules cannot rerun ingestion. Other
    exceptions must disappear from the verification pass before a correction resolves them.
    """
    return exception.rule_id in INGESTION_RULE_IDS or exception.exception_id not in verification_ids


def build_queue(
    exceptions: list[ExceptionRow], config: ConfigBundle, overrides: OverrideOutcome,
    verification: tuple[ExceptionRow, ...],
) -> QueueOutcome:
    """Retain filed evidence, resolve successful decisions, and add verification failures.

    Filed exceptions win when both passes raise the same ID: corrections must not rewrite
    the original evidence. A failure first seen during verification remains open.
    """
    by_id = {r.exception_id: r for r in config.resolutions}
    raised_ids = {e.exception_id for e in exceptions}
    override_ids = {o.exception_id for o in overrides.applied}
    verification_ids = {e.exception_id for e in verification}

    resolved: list[ExceptionRow] = []
    excluded: list[tuple[str, str]] = []
    applied: list[Resolution] = []

    for exception in exceptions:
        resolution = by_id.get(exception.exception_id)
        if resolution is None:
            resolved.append(exception)
            continue
        if resolution.decision == "correct" and (
            exception.exception_id not in override_ids
            or not _correction_cleared(exception, verification_ids)
        ):
            resolved.append(exception)
            continue
        applied.append(resolution)
        if resolution.decision == "exclude":
            excluded.append((exception.holding_id, exception.period_label))
        resolved.append(
            exception.model_copy(
                update={
                    "status": f"resolved:{resolution.decision}",
                    "resolution_decision": resolution.decision,
                    "resolution_reviewer": resolution.reviewer,
                    "resolution_rationale": resolution.rationale,
                }
            )
        )

    notices = [_unanchored_exception(r, config) for r in overrides.unanchored]
    for resolution in config.resolutions:
        if resolution.exception_id in raised_ids or resolution.decision == "correct":
            continue
        notices.append(
            _stale_exception(
                resolution,
                config,
                "matched no exception raised on the as-filed data.",
            )
        )
    for resolution in overrides.unmatched:
        notices.append(
            _stale_exception(resolution, config, "targets a canonical row that does not exist.")
        )

    new_failures = [e for e in verification if e.exception_id not in raised_ids]
    return QueueOutcome(
        exceptions=tuple(sorted(resolved + notices + new_failures, key=lambda e: e.exception_id)),
        excluded=tuple(sorted(set(excluded))),
        resolutions_applied=tuple(
            sorted({r.exception_id: r for r in applied}.values(), key=lambda r: r.exception_id)
        ),
    )


@dataclass(frozen=True)
class GateResult:
    passed: bool
    blocking: tuple[ExceptionRow, ...]

    def message(self) -> str:
        if self.passed:
            return "GATE PASS - no open blocking exceptions."
        lines = [f"GATE HELD - {len(self.blocking)} open blocking exception(s):"]
        for exception in self.blocking:
            lines.append(
                f"  {exception.exception_id}  [{exception.rule_id}] "
                f"{exception.holding_id} {exception.period_label}: {exception.evidence}"
            )
        lines.append("Add a decision for each in config/resolutions.yaml and rerun.")
        return "\n".join(lines)


def evaluate_gate(queue: QueueOutcome) -> GateResult:
    """The report is only built when no blocking exception is still open."""
    blocking = tuple(
        e for e in queue.exceptions if e.severity == "block" and e.status == "open"
    )
    return GateResult(passed=not blocking, blocking=blocking)
