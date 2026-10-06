"""The data contract: every shape that crosses a stage boundary is declared here.

These models are the reason a bad value cannot drift through the pipeline unnoticed.
Validation is strict on purpose - a string where a float belongs is a defect in the
source file or the parser, not something to coerce quietly.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Severity = Literal["block", "warn"]
Decision = Literal["accept", "correct", "exclude"]
RecordType = Literal["metric", "cap_table", "lp_capital", "fund_summary"]
# Canonical table names, which are plural for metrics - a resolution targets a table, not a record.
CanonicalTable = Literal["metrics", "cap_table", "lp_capital", "fund_summary"]

FUND_ENTITY = "FUND"


class Frozen(BaseModel):
    """Base for every contract model: immutable, and extra keys are an error.

    Immutability matters because rule functions receive canonical rows and must not be
    able to edit them; forbidding extra keys turns a renamed field into a loud failure.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- config


class Period(Frozen):
    label: str
    period_end: date
    months: list[str]


class Holding(Frozen):
    holding_id: str
    name: str
    asset_class: str
    template: str
    report_format: str
    invested_capital_usd: int
    entry_date: date


class FundMeta(Frozen):
    fund_id: str
    name: str
    vintage: int
    total_commitments_usd: int
    lp_count: int


class DefectSpec(Frozen):
    id: str
    enabled: bool
    description: str
    holding_id: str
    period: str
    expected_rule: str


class FundConfig(Frozen):
    seed: int
    fund: FundMeta
    periods: list[Period]
    holdings: list[Holding]
    defects: list[DefectSpec]

    def holding(self, holding_id: str) -> Holding:
        for h in self.holdings:
            if h.holding_id == holding_id:
                return h
        raise KeyError(f"unknown holding_id {holding_id!r} in config/fund.yaml")

    def period(self, label: str) -> Period:
        for p in self.periods:
            if p.label == label:
                return p
        raise KeyError(f"unknown period {label!r} in config/fund.yaml")


class LabelMapping(Frozen):
    metric: str


class ScaleOverride(Frozen):
    period: str
    scale: Literal["dollars", "thousands"]


class MappingConfig(Frozen):
    template: str
    mapping_version: str
    unit_scale: Literal["dollars", "thousands"]
    scale_overrides: list[ScaleOverride] = Field(default_factory=list)
    labels: dict[str, LabelMapping]
    ignore_labels: list[str]

    def declared_scale(self, period_label: str) -> str:
        """Scale the mapping says to expect for a period, so R07 can tell a declared
        restatement from a silent one."""
        for override in self.scale_overrides:
            if override.period == period_label:
                return override.scale
        return self.unit_scale


class MetricSpec(Frozen):
    unit: Literal["USD", "PCT"]
    frequency: Literal["monthly", "quarterly"]
    label: str


class MetricDictionary(Frozen):
    metrics: dict[str, dict[str, MetricSpec]]

    def spec(self, asset_class: str, metric: str) -> MetricSpec:
        return self.metrics[asset_class][metric]


class AssetClassPresentation(Frozen):
    """How one asset class is introduced on the summary."""

    tab_label: str
    short_label: str
    unit_noun: str
    headline_metric: str
    headline_caption: str
    aggregate_metrics: list[str]
    lower_is_better: list[str] = Field(default_factory=list)
    neutral_metrics: list[str] = Field(default_factory=list)

    def sentiment_for(self, metric: str, change: float | None) -> str:
        """Whether a move in this metric reads as good, bad, or neither."""
        if change is None or change == 0 or metric in self.neutral_metrics:
            return "neutral"
        improving = change < 0 if metric in self.lower_is_better else change > 0
        return "good" if improving else "bad"


class PresentationConfig(Frozen):
    asset_classes: dict[str, AssetClassPresentation]


class Tolerance(Frozen):
    kind: str
    value: float | None = None
    low: float | None = None
    high: float | None = None


class RuleSpec(Frozen):
    enabled: bool
    severity: Severity
    name: str
    description: str
    tolerance: Tolerance


class RulesConfig(Frozen):
    rules: dict[str, RuleSpec]

    def spec(self, rule_id: str) -> RuleSpec:
        return self.rules[rule_id]

    def is_enabled(self, rule_id: str) -> bool:
        return self.rules[rule_id].enabled


class ResolutionTarget(Frozen):
    """Which canonical cell a `correct` decision overrides.

    Spelled out explicitly rather than inferred from the exception, because inferring it
    would make the audit trail depend on rule internals.
    """

    table: CanonicalTable
    keys: dict[str, str]
    column: str


class Resolution(Frozen):
    exception_id: str
    decision: Decision
    reviewer: str
    date: date
    rationale: str
    source: str | None = None
    target: ResolutionTarget | None = None
    corrected_value: float | None = None

    @field_validator("rationale")
    @classmethod
    def _rationale_is_substantive(cls, v: str) -> str:
        """A one-word rationale is not a sign-off; the gate should not accept one."""
        if len(v.strip()) < 15:
            raise ValueError("rationale must be a real sentence (>= 15 characters)")
        return v


# ------------------------------------------------------------------------- canonical


class Lineage(Frozen):
    """Where a canonical value came from. Attached to every source-derived row."""

    source_file: str
    source_sheet: str | None
    source_ref: str
    file_sha256: str
    run_id: str
    mapping_version: str
    override_of: str | None = None  # exception_id when the value came from a resolution
    override_source: str | None = None  # what the reviewer cited for the corrected value
    original_value: float | None = None  # the filed value this override replaced


class MetricRow(Frozen):
    holding_id: str
    period_end: date
    period_label: str
    metric: str
    value: float
    unit: str
    frequency: str
    sub_period: str  # "2026Q2" for quarterly metrics, "2026-05" for monthly
    lineage: Lineage


class CapTableRow(Frozen):
    holding_id: str
    period_end: date
    period_label: str
    holder: str
    share_class: str
    shares: float
    ownership_pct: float
    lineage: Lineage


class LPCapitalRow(Frozen):
    lp_id: str
    period_end: date
    period_label: str
    commitment_usd: float
    called_usd: float
    distributed_usd: float
    lineage: Lineage


class FundSummaryRow(Frozen):
    period_end: date
    period_label: str
    total_commitments_usd: float
    total_called_usd: float
    lineage: Lineage


class ExceptionRow(Frozen):
    """One rule failure, with enough evidence to be understood without opening the source."""

    exception_id: str
    rule_id: str
    severity: Severity
    holding_id: str  # FUND for fund-level rules
    period_label: str
    period_end: date | None
    subject: str  # metric, holder, label - whatever the rule compared
    evidence: str
    expected: float | None = None
    observed: float | None = None
    difference: float | None = None
    lineage_refs: tuple[str, ...] = ()
    status: str = "open"
    resolution_decision: Decision | None = None
    resolution_reviewer: str | None = None
    resolution_rationale: str | None = None
