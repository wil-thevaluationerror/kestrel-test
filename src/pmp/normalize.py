"""Map source labels onto the canonical schema and attach lineage.

Three things happen here and nowhere else: a source label becomes a canonical metric, a
text cell becomes a number, and every canonical value acquires the address it came from.

An unmapped label becomes an I01 exception. It is never guessed at and never dropped
quietly - the value simply does not enter the canonical tables, and the gate will hold the
report until a reviewer decides what it was.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .configio import ConfigBundle
from .contract import (
    FUND_ENTITY,
    CapTableRow,
    ExceptionRow,
    FundSummaryRow,
    Lineage,
    LPCapitalRow,
    MetricRow,
)
from .ids import exception_id
from .ingest import StagedReport, StagedRow


class NormalizeError(RuntimeError):
    """A source value could not be typed, or two sources claim the same canonical cell.

    Raised rather than recorded, because both cases mean the pipeline cannot describe the
    data honestly - and a pipeline that cannot describe the data must stop, not guess.
    """


@dataclass(frozen=True)
class Canonical:
    metrics: tuple[MetricRow, ...] = ()
    cap_table: tuple[CapTableRow, ...] = ()
    lp_capital: tuple[LPCapitalRow, ...] = ()
    fund_summary: tuple[FundSummaryRow, ...] = ()


@dataclass
class _Accumulator:
    metrics: list[MetricRow] = field(default_factory=list)
    cap_table: list[CapTableRow] = field(default_factory=list)
    lp_capital: list[LPCapitalRow] = field(default_factory=list)
    fund_summary: list[FundSummaryRow] = field(default_factory=list)
    exceptions: list[ExceptionRow] = field(default_factory=list)


def _to_float(row: StagedRow) -> float:
    try:
        return float(str(row.raw_value).replace(",", "").replace("$", ""))
    except ValueError as exc:
        raise NormalizeError(
            f"{row.source_file} [{row.source_sheet or 'csv'}!{row.source_ref}]: "
            f"cannot read {row.raw_value!r} as a number for label {row.source_label!r}"
        ) from exc


def _lineage(row: StagedRow, run_id: str, mapping_version: str) -> Lineage:
    return Lineage(
        source_file=row.source_file,
        source_sheet=row.source_sheet,
        source_ref=row.source_ref,
        file_sha256=row.file_sha256,
        run_id=run_id,
        mapping_version=mapping_version,
    )


def _unmapped_label_exception(row: StagedRow, period_end, rule_severity: str) -> ExceptionRow:
    return ExceptionRow(
        exception_id=exception_id(row.period_label, row.holding_id, "I01", row.source_label),
        rule_id="I01",
        severity=rule_severity,
        holding_id=row.holding_id,
        period_label=row.period_label,
        period_end=period_end,
        subject=row.source_label,
        evidence=(
            f"Source label {row.source_label!r} has no mapping entry for template; "
            f"value {row.raw_value!r} at {row.source_file} "
            f"[{row.source_sheet or 'csv'}!{row.source_ref}] was not loaded."
        ),
        lineage_refs=(f"{row.source_file}[{row.source_sheet or 'csv'}!{row.source_ref}]",),
    )


def _group_rows(rows: list[StagedRow], key_fields: tuple[str, ...]) -> dict[tuple, dict[str, StagedRow]]:
    """Collect the per-field staged cells that make up one canonical row."""
    grouped: dict[tuple, dict[str, StagedRow]] = {}
    for row in rows:
        key = tuple(getattr(row, name) for name in key_fields)
        grouped.setdefault(key, {})[row.field] = row
    return grouped


def _require(cells: dict[str, StagedRow], field_name: str, context: str) -> StagedRow:
    if field_name not in cells:
        raise NormalizeError(f"{context}: missing column {field_name!r} in source file")
    return cells[field_name]


def _normalize_metrics(
    staged: list[StagedRow], config: ConfigBundle, run_id: str, acc: _Accumulator
) -> None:
    """Map each line-item cell onto a canonical metric, or raise I01 and withhold it."""
    i01_severity = config.rules.spec("I01").severity
    i01_enabled = config.rules.is_enabled("I01")
    seen: dict[tuple, str] = {}

    for row in [r for r in staged if r.record_type == "metric"]:
        holding = config.fund.holding(row.holding_id)
        mapping = config.mapping_for(holding.template)
        period_end = config.fund.period(row.period_label).period_end

        if row.source_label in mapping.ignore_labels:
            continue
        if row.source_label not in mapping.labels:
            if i01_enabled:
                acc.exceptions.append(_unmapped_label_exception(row, period_end, i01_severity))
            continue

        metric = mapping.labels[row.source_label].metric
        try:
            spec = config.dictionary.spec(holding.asset_class, metric)
        except KeyError as exc:
            raise NormalizeError(
                f"mapping {mapping.template} maps {row.source_label!r} to {metric!r}, which is "
                f"not in the metric dictionary for asset class {holding.asset_class!r}"
            ) from exc

        key = (row.holding_id, row.period_label, metric, row.source_period)
        address = f"{row.source_file}[{row.source_sheet or 'csv'}!{row.source_ref}]"
        if key in seen:
            raise NormalizeError(
                f"two sources claim {key}: {seen[key]} and {address}. "
                "Restatements must be withdrawn and resubmitted, not filed alongside."
            )
        seen[key] = address

        acc.metrics.append(
            MetricRow(
                holding_id=row.holding_id,
                period_end=period_end,
                period_label=row.period_label,
                metric=metric,
                value=_to_float(row),
                unit=spec.unit,
                frequency=spec.frequency,
                sub_period=row.source_period,
                lineage=_lineage(row, run_id, mapping.mapping_version),
            )
        )


def _normalize_cap_table(
    staged: list[StagedRow], config: ConfigBundle, run_id: str, acc: _Accumulator
) -> None:
    for (holding_id, period_label, holder), cells in _group_rows(
        [r for r in staged if r.record_type == "cap_table"],
        ("holding_id", "period_label", "source_label"),
    ).items():
        mapping = config.mapping_for(config.fund.holding(holding_id).template)
        context = f"cap table {holding_id} {period_label} {holder}"
        pct_cell = _require(cells, "ownership_pct", context)
        acc.cap_table.append(
            CapTableRow(
                holding_id=holding_id,
                period_end=config.fund.period(period_label).period_end,
                period_label=period_label,
                holder=holder,
                share_class=str(_require(cells, "share_class", context).raw_value),
                shares=_to_float(_require(cells, "shares", context)),
                ownership_pct=_to_float(pct_cell),
                # Lineage points at the ownership cell: it is the number R04 compares.
                lineage=_lineage(pct_cell, run_id, mapping.mapping_version),
            )
        )


def _normalize_lp_capital(
    staged: list[StagedRow], config: ConfigBundle, run_id: str, acc: _Accumulator
) -> None:
    for (lp_id, period_label), cells in _group_rows(
        [r for r in staged if r.record_type == "lp_capital"], ("entity_id", "period_label")
    ).items():
        context = f"lp capital {lp_id} {period_label}"
        called_cell = _require(cells, "called_usd", context)
        acc.lp_capital.append(
            LPCapitalRow(
                lp_id=lp_id,
                period_end=config.fund.period(period_label).period_end,
                period_label=period_label,
                commitment_usd=_to_float(_require(cells, "commitment_usd", context)),
                called_usd=_to_float(called_cell),
                distributed_usd=_to_float(_require(cells, "distributed_usd", context)),
                lineage=_lineage(called_cell, run_id, "n/a"),
            )
        )


def _normalize_fund_summary(
    staged: list[StagedRow], config: ConfigBundle, run_id: str, acc: _Accumulator
) -> None:
    for (_, period_label), cells in _group_rows(
        [r for r in staged if r.record_type == "fund_summary"], ("entity_id", "period_label")
    ).items():
        context = f"fund summary {period_label}"
        called_cell = _require(cells, "total_called_usd", context)
        acc.fund_summary.append(
            FundSummaryRow(
                period_end=config.fund.period(period_label).period_end,
                period_label=period_label,
                total_commitments_usd=_to_float(_require(cells, "total_commitments_usd", context)),
                total_called_usd=_to_float(called_cell),
                lineage=_lineage(called_cell, run_id, "n/a"),
            )
        )


def normalize(
    reports: list[StagedReport], config: ConfigBundle, run_id: str
) -> tuple[Canonical, list[ExceptionRow]]:
    """Turn staged cells into canonical rows plus any I01 exceptions."""
    acc = _Accumulator()
    staged = [row for report in reports for row in report.rows]

    _normalize_metrics(staged, config, run_id, acc)
    _normalize_cap_table(staged, config, run_id, acc)
    _normalize_lp_capital(staged, config, run_id, acc)
    _normalize_fund_summary(staged, config, run_id, acc)

    canonical = Canonical(
        metrics=tuple(acc.metrics),
        cap_table=tuple(acc.cap_table),
        lp_capital=tuple(acc.lp_capital),
        fund_summary=tuple(acc.fund_summary),
    )
    return canonical, acc.exceptions


def duplicate_exceptions(duplicates, config: ConfigBundle) -> list[ExceptionRow]:
    """I02: a file whose bytes were already ingested for this holding and period."""
    if not config.rules.is_enabled("I02"):
        return []
    severity = config.rules.spec("I02").severity
    out: list[ExceptionRow] = []
    for dup in duplicates:
        out.append(
            ExceptionRow(
                exception_id=exception_id(dup.period_label, dup.holding_id, "I02"),
                rule_id="I02",
                severity=severity,
                holding_id=dup.holding_id,
                period_label=dup.period_label,
                period_end=config.fund.period(dup.period_label).period_end,
                subject=dup.path.name,
                evidence=(
                    f"{dup.path.name} is byte-identical to {dup.first_seen} "
                    f"(sha256 {dup.file_sha256[:12]}...). The second submission was not loaded."
                ),
                lineage_refs=(dup.first_seen, str(dup.path.name)),
            )
        )
    return out
