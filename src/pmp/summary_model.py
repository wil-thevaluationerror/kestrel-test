"""The shape of the fund summary, built before anything is rendered.

Separating the model from the template means the lineage test can assert that every number
on the page carries a trace, without parsing HTML.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

@dataclass(frozen=True)
class TraceRef:
    """One openable origin of a figure.

    Structured rather than a formatted string so the summary can resolve it to a document
    preview and a download, and so the lineage test can check the parts instead of a regex.
    """

    kind: str  # cell | resolution | config
    file: str  # repo-relative path of the document
    sheet: str | None
    ref: str  # the cell reference, matching the keys in the source preview grid
    sha256: str
    label: str  # the one-line form, used for the hover title and the print appendix
    exception_id: str | None = None  # set when the origin is a reviewer decision


@dataclass(frozen=True)
class TracedValue:
    """A number that knows where it came from. `traces` is never empty by construction."""

    value: float | None
    unit: str
    traces: tuple[TraceRef, ...]
    overridden: bool = False
    override_note: str | None = None

    def __post_init__(self) -> None:
        if self.value is not None and not self.traces:
            raise ValueError("a reported value must carry at least one trace")


@dataclass(frozen=True)
class MetricLine:
    metric: str
    label: str
    unit: str
    prior: TracedValue
    current: TracedValue
    change_pct: float | None
    change_display: str
    sentiment: str = "neutral"  # good | bad | neutral - see config/presentation.yaml


@dataclass(frozen=True)
class HoldingPanel:
    holding_id: str
    name: str
    asset_class: str
    invested_capital: TracedValue
    entry_date: date
    lines: tuple[MetricLine, ...]
    headline: MetricLine | None = None  # the figure the card leads with
    corrections: int = 0  # figures on this card that a reviewer changed
    note: str | None = None


@dataclass(frozen=True)
class SectionStat:
    """One aggregate across the holdings in a tab, carrying the cells it was summed from."""

    label: str
    traced: TracedValue
    change_display: str
    change_pct: float | None
    sentiment: str = "neutral"


@dataclass(frozen=True)
class AssetClassSection:
    asset_class: str
    label: str
    short_label: str
    unit_noun: str
    headline_caption: str
    panels: tuple[HoldingPanel, ...]
    stats: tuple[SectionStat, ...] = ()
    invested: TracedValue | None = None
    corrections: int = 0


@dataclass(frozen=True)
class FundPanel:
    commitments: TracedValue
    called: TracedValue
    called_pct: float | None
    lp_count: int


@dataclass(frozen=True)
class ResolutionLine:
    exception_id: str
    rule_id: str
    decision: str
    reviewer: str
    date: date
    rationale: str
    detail: str


@dataclass(frozen=True)
class Summary:
    fund_name: str
    period_label: str
    period_end: date
    prior_period_label: str
    run_id: str
    generated_at: str
    git_commit: str
    gate_passed: bool
    fund_panel: FundPanel
    sections: tuple[AssetClassSection, ...]
    warnings: tuple[str, ...] = ()
    resolutions: tuple[ResolutionLine, ...] = ()
    not_checked: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    traced_values: tuple[TracedValue, ...] = field(default=())
    source_index: dict = field(default_factory=dict)
