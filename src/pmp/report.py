"""Outputs: the fund summary, the exception register, and the run manifest.

The summary is built from canonical rows only. Anything a reviewer sees on the page carries
the file, sheet, cell, and hash it came from, or the resolution that replaced it.
"""

from __future__ import annotations

import csv
import io
import json
import subprocess

import yaml
from dataclasses import asdict
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from .configio import ConfigBundle
from .contract import ExceptionRow, Resolution
from .exceptions import AppliedOverride, GateResult, QueueOutcome
from .normalize import Canonical
from .paths import Layout
from .sources import SourceBundle
from .summary_model import (
    AssetClassSection,
    FundPanel,
    HoldingPanel,
    MetricLine,
    ResolutionLine,
    SectionStat,
    Summary,
    TracedValue,
    TraceRef,
)
from .textio import write_text

CONFIG_FILE = "config/fund.yaml"
CONFIG_REF = "holdings"
CONFIG_TRACE = f"{CONFIG_FILE}#{CONFIG_REF}"


def git_commit(layout: Layout) -> str:
    """Record which code produced the run. 'unknown' rather than a crash outside a checkout."""
    try:
        result = subprocess.run(
            ["git", "-C", str(layout.root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return result.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "unknown"


def _address(lineage) -> str:
    sheet = lineage.source_sheet or "csv"
    return f"{lineage.source_file}[{sheet}!{lineage.source_ref}] sha256:{lineage.file_sha256[:12]}"


def _cell_trace(lineage) -> TraceRef:
    return TraceRef(
        kind="cell",
        file=lineage.source_file,
        sheet=lineage.source_sheet,
        ref=lineage.source_ref,
        sha256=lineage.file_sha256,
        label=_address(lineage),
    )


def _resolution_trace(lineage, resolutions_file: str, resolutions_sha: str) -> TraceRef:
    """The decision record behind an overridden figure, openable like any other source."""
    return TraceRef(
        kind="resolution",
        file=resolutions_file,
        sheet=None,
        ref=lineage.override_of,
        sha256=resolutions_sha,
        label=f"{resolutions_file}[{lineage.override_of}]",
        exception_id=lineage.override_of,
    )


def _traced(rows: list, config: ConfigBundle | None = None) -> TracedValue | None:
    """Sum a set of canonical rows into one reported figure, carrying every source cell.

    An overridden figure carries two origins: the cell as filed, and the decision that
    changed it. Showing only the second would hide what the company actually sent.
    """
    if not rows:
        return None
    total = sum(row.value for row in rows)
    traces: list[TraceRef] = []
    overridden = False
    notes: list[str] = []
    resolutions_file = config.resolutions_file if config else ""
    resolutions_sha = config.resolutions_sha256 if config else ""
    for row in rows:
        supplied_by_reviewer = row.lineage.source_file == resolutions_file
        if not supplied_by_reviewer:
            traces.append(_cell_trace(row.lineage))
        if row.lineage.override_of:
            overridden = True
            # A corrected cell keeps both origins; a value the file never carried in mappable
            # form has only the decision record to point at.
            traces.append(_resolution_trace(row.lineage, resolutions_file, resolutions_sha))
            filed = (
                f"filed {row.lineage.original_value:,.2f}"
                if row.lineage.original_value is not None
                else "not reported in mappable form"
            )
            notes.append(
                f"{row.lineage.override_of}: {filed} -> {row.value:,.2f} "
                f"({row.lineage.override_source})"
            )
    return TracedValue(
        value=float(total),
        unit=rows[0].unit,
        traces=tuple(traces),
        overridden=overridden,
        override_note="; ".join(notes) or None,
    )


EMPTY = TracedValue(
    value=None,
    unit="",
    traces=(TraceRef(kind="none", file="", sheet=None, ref="", sha256="", label="not reported"),),
)


def _change(prior: TracedValue, current: TracedValue, unit: str) -> tuple[float | None, str]:
    """Percentage change for money, percentage points for rates.

    A percentage change in an occupancy rate is close to meaningless; the number a property
    team argues about is the point move.
    """
    if prior.value is None or current.value is None:
        return None, "—"
    if unit == "PCT":
        delta = current.value - prior.value
        return delta, f"{delta:+,.1f} pp"
    if prior.value == 0:
        return None, "n/m"
    change = (current.value - prior.value) / abs(prior.value) * 100.0
    return change, f"{change:+,.1f}%"


def _metric_lines(
    canonical: Canonical, config: ConfigBundle, holding, prior_label: str, current_label: str
) -> tuple[MetricLine, ...]:
    """One line per canonical metric in dictionary order.

    Monthly metrics are summed to the quarter, and every month's cell stays in the trace, so
    a quarterly revenue figure can still be walked back to three source rows.
    """
    specs = config.dictionary.metrics[holding.asset_class]
    lines: list[MetricLine] = []
    for metric, spec in specs.items():
        def rows_for(period_label: str) -> list:
            return sorted(
                (
                    row
                    for row in canonical.metrics
                    if row.holding_id == holding.holding_id
                    and row.period_label == period_label
                    and row.metric == metric
                ),
                key=lambda row: row.sub_period,
            )

        prior = _traced(rows_for(prior_label), config) or EMPTY
        current = _traced(rows_for(current_label), config) or EMPTY
        label = spec.label + (" (quarter total)" if spec.frequency == "monthly" else "")
        change_pct, change_display = _change(prior, current, spec.unit)
        settings = config.presentation.asset_classes[holding.asset_class]
        lines.append(
            MetricLine(
                metric=metric,
                label=label,
                unit=spec.unit,
                prior=prior,
                current=current,
                change_pct=change_pct,
                change_display=change_display,
                sentiment=settings.sentiment_for(metric, change_pct),
            )
        )
    return tuple(lines)


def _config_trace(config: ConfigBundle) -> TraceRef:
    return TraceRef(
        kind="config", file=CONFIG_FILE, sheet=None, ref=CONFIG_REF,
        sha256=config.config_hashes.get(CONFIG_FILE, ""), label=CONFIG_TRACE,
    )


def _aggregate(
    canonical: Canonical, config: ConfigBundle, holding_ids: list[str], metric: str,
    period_label: str,
) -> TracedValue | None:
    """Sum one metric across the holdings in a tab, keeping every source cell behind it.

    An aggregate is still a number on the page, so it carries its lineage like any other.
    """
    rows = sorted(
        (
            row
            for row in canonical.metrics
            if row.holding_id in holding_ids
            and row.period_label == period_label
            and row.metric == metric
        ),
        key=lambda row: (row.holding_id, row.sub_period),
    )
    return _traced(rows, config)


def _section_stats(
    canonical: Canonical, config: ConfigBundle, asset_class: str, holding_ids: list[str],
    prior_label: str, period_label: str,
) -> tuple[SectionStat, ...]:
    """The overview strip at the top of a tab, driven by config/presentation.yaml."""
    settings = config.presentation.asset_classes[asset_class]
    stats: list[SectionStat] = []
    for metric in settings.aggregate_metrics:
        spec = config.dictionary.spec(asset_class, metric)
        current = _aggregate(canonical, config, holding_ids, metric, period_label)
        if current is None:
            continue
        prior = _aggregate(canonical, config, holding_ids, metric, prior_label) or EMPTY
        change_pct, change_display = _change(prior, current, spec.unit)
        stats.append(
            SectionStat(
                label=spec.label + (" (quarter)" if spec.frequency == "monthly" else ""),
                traced=current,
                change_display=change_display,
                change_pct=change_pct,
                sentiment=settings.sentiment_for(metric, change_pct),
            )
        )
    return tuple(stats)


def _fund_panel(canonical: Canonical, config: ConfigBundle, period_label: str) -> FundPanel:
    rows = [r for r in canonical.fund_summary if r.period_label == period_label]
    if not rows:
        raise ValueError(f"no fund summary row loaded for {period_label}")
    row = rows[0]
    trace = _cell_trace(row.lineage)
    commitments = TracedValue(row.total_commitments_usd, "USD", (trace,))
    called = TracedValue(
        row.total_called_usd,
        "USD",
        (trace,),
        overridden=bool(row.lineage.override_of),
        override_note=row.lineage.override_of,
    )
    called_pct = (
        row.total_called_usd / row.total_commitments_usd * 100.0
        if row.total_commitments_usd
        else None
    )
    lp_count = len({r.lp_id for r in canonical.lp_capital if r.period_label == period_label})
    return FundPanel(commitments=commitments, called=called, called_pct=called_pct, lp_count=lp_count)


def _resolution_lines(
    resolutions: tuple[Resolution, ...], overrides: tuple[AppliedOverride, ...]
) -> tuple[ResolutionLine, ...]:
    override_by_id: dict[str, list[AppliedOverride]] = {}
    for override in overrides:
        override_by_id.setdefault(override.exception_id, []).append(override)

    lines: list[ResolutionLine] = []
    for resolution in resolutions:
        details = [
            f"{o.table}.{o.column} ({', '.join(str(v) for v in o.keys.values())}): "
            f"{'not reported' if o.original_value is None else format(o.original_value, ',.2f')}"
            f" \u2192 {o.corrected_value:,.2f}"
            for o in override_by_id.get(resolution.exception_id, [])
        ]
        lines.append(
            ResolutionLine(
                exception_id=resolution.exception_id,
                rule_id=resolution.exception_id.split("-")[-1],
                decision=resolution.decision,
                reviewer=resolution.reviewer,
                date=resolution.date,
                rationale=resolution.rationale,
                detail="; ".join(details) or (resolution.source or ""),
            )
        )
    return tuple(lines)


def _document_payload(document) -> dict:
    return {
        "filename": document.filename,
        "sha256": document.sha256,
        "kind": document.kind,
        "download": document.download,
        "note": document.note,
        "text": document.text,
        "sheets": [
            {
                "name": sheet.name,
                "columns": list(sheet.columns),
                "truncated": sheet.truncated,
                "rows": [[{"ref": cell.ref, "text": cell.text} for cell in row] for row in sheet.rows],
            }
            for sheet in document.sheets
        ],
    }


def _resolution_payload(config: ConfigBundle, document) -> dict:
    """Each decision as the YAML a reviewer would read, keyed by the exception it answers."""
    payload: dict[str, dict] = {}
    for resolution in config.resolutions:
        record = json.loads(resolution.model_dump_json(exclude_none=True))
        payload[resolution.exception_id] = {
            "file": config.resolutions_file,
            "download": document.download if document else None,
            "decision": resolution.decision,
            "reviewer": resolution.reviewer,
            "date": str(resolution.date),
            "yaml": yaml.safe_dump(record, sort_keys=False, default_flow_style=False),
        }
    return payload


def build_source_index(sources: SourceBundle, config: ConfigBundle) -> dict:
    """Everything the summary needs to open a trace without going back to the filesystem.

    Embedded in the page rather than fetched, so the report still works when it is filed,
    emailed, or opened from disk a year from now.
    """
    return {
        "files": {
            path: _document_payload(document)
            for path, document in sorted(sources.documents.items())
        },
        "resolutions": _resolution_payload(config, sources.get(config.resolutions_file)),
    }


def build_summary(
    *, canonical: Canonical, config: ConfigBundle, queue: QueueOutcome,
    overrides: tuple[AppliedOverride, ...], gate: GateResult, run_id: str,
    generated_at: str, commit: str, not_checked: tuple[str, ...], period_label: str,
    prior_label: str, sources: SourceBundle,
) -> Summary:
    """Assemble the page model. Raises if a figure would be shown without a trace."""
    excluded_keys = set(queue.excluded)
    sections: list[AssetClassSection] = []
    traced: list[TracedValue] = []

    for asset_class, settings in config.presentation.asset_classes.items():
        panels: list[HoldingPanel] = []
        for holding in config.fund.holdings:
            if holding.asset_class != asset_class:
                continue
            if (holding.holding_id, period_label) in excluded_keys:
                continue
            lines = _metric_lines(canonical, config, holding, prior_label, period_label)
            invested = TracedValue(
                float(holding.invested_capital_usd), "USD", (_config_trace(config),)
            )
            headline = next(
                (line for line in lines if line.metric == settings.headline_metric), None
            )
            panels.append(
                HoldingPanel(
                    holding_id=holding.holding_id,
                    name=holding.name,
                    asset_class=asset_class,
                    invested_capital=invested,
                    entry_date=holding.entry_date,
                    lines=lines,
                    headline=headline,
                    corrections=sum(1 for line in lines if line.current.overridden),
                )
            )
            traced.append(invested)
            for line in lines:
                traced.extend(v for v in (line.prior, line.current) if v.value is not None)

        holding_ids = [panel.holding_id for panel in panels]
        stats = _section_stats(
            canonical, config, asset_class, holding_ids, prior_label, period_label
        )
        traced.extend(stat.traced for stat in stats)
        invested_total = TracedValue(
            float(
                sum(
                    config.fund.holding(holding_id).invested_capital_usd
                    for holding_id in holding_ids
                )
            ),
            "USD",
            (_config_trace(config),),
        ) if holding_ids else None
        if invested_total is not None:
            traced.append(invested_total)

        sections.append(
            AssetClassSection(
                asset_class=asset_class,
                label=settings.tab_label,
                short_label=settings.short_label,
                unit_noun=settings.unit_noun,
                headline_caption=settings.headline_caption,
                panels=tuple(panels),
                stats=stats,
                invested=invested_total,
                corrections=sum(panel.corrections for panel in panels),
            )
        )

    fund_panel = _fund_panel(canonical, config, period_label)
    traced.extend([fund_panel.commitments, fund_panel.called])

    warnings = tuple(
        f"[{e.rule_id}] {e.holding_id} {e.period_label} {e.subject}: {e.evidence}"
        for e in queue.exceptions
        if e.severity == "warn" and e.status == "open"
    )
    excluded = tuple(
        f"{holding_id} held out of {label} by reviewer decision"
        for holding_id, label in queue.excluded
    )

    return Summary(
        fund_name=config.fund.fund.name,
        period_label=period_label,
        period_end=config.fund.period(period_label).period_end,
        prior_period_label=prior_label,
        run_id=run_id,
        generated_at=generated_at,
        git_commit=commit,
        gate_passed=gate.passed,
        fund_panel=fund_panel,
        sections=tuple(sections),
        warnings=warnings,
        resolutions=_resolution_lines(queue.resolutions_applied, overrides),
        not_checked=not_checked,
        excluded=excluded,
        traced_values=tuple(traced),
        source_index=build_source_index(sources, config),
    )


# --------------------------------------------------------------------------- rendering


def _fmt_value(value: float | None, unit: str) -> str:
    """Accounting presentation: negatives in parentheses, which is how a fund reads them."""
    if value is None:
        return "—"
    if unit == "PCT":
        return f"{value:,.1f}%"
    if value < 0:
        return f"(${abs(value):,.0f})"
    return f"${value:,.0f}"


def _embed_json(payload: dict) -> str:
    """Serialise for a <script type="application/json"> block.

    The angle brackets and ampersand are escaped as JSON unicode escapes so the payload can
    never close the script element early, and so the template can emit it without autoescaping
    (which would turn every quote into an entity and break JSON.parse in the browser).
    """
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _traces_json(traced: TracedValue) -> str:
    """Attach a value's origins to its button, so the dialog needs no server to resolve them."""
    return json.dumps([asdict(trace) for trace in traced.traces], sort_keys=True)


def render_summary(summary: Summary, layout: Layout) -> str:
    environment = Environment(
        loader=FileSystemLoader(layout.templates),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    environment.filters["money"] = _fmt_value
    environment.filters["traces"] = _traces_json
    return environment.get_template("summary.html.j2").render(
        summary=summary,
        source_index_json=Markup(_embed_json(summary.source_index)),
    )


# ----------------------------------------------------------------------------- writers

EXCEPTION_COLUMNS = (
    "exception_id", "rule_id", "severity", "status", "holding_id", "period_label",
    "subject", "expected", "observed", "difference", "resolution_decision",
    "resolution_reviewer", "resolution_rationale", "evidence", "lineage_refs",
)


def write_exceptions_csv(exceptions: tuple[ExceptionRow, ...], path: Path) -> Path:
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=list(EXCEPTION_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for exception in exceptions:
        payload = exception.model_dump()
        payload["lineage_refs"] = " | ".join(payload.get("lineage_refs") or ())
        writer.writerow({column: payload.get(column, "") for column in EXCEPTION_COLUMNS})
    write_text(path, buffer.getvalue())
    return path


def write_manifest(payload: dict, path: Path) -> Path:
    write_text(path, json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    return path


def summary_to_dict(summary: Summary) -> dict:
    """Used by tests and by anyone who wants the page as data instead of HTML."""
    return asdict(summary)


def today_iso() -> str:
    return date.today().isoformat()
