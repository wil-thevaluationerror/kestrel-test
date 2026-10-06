"""R07 - a silent change of units.

A USD metric that moves by roughly 1,000x between quarters is almost never a business
event; it is a template switched to thousands. The mapping has to declare a scale change,
so an undeclared one is the signal. This is the rule that catches D08, and it is the one
most likely to matter on real data.
"""

from __future__ import annotations

from ..contract import ExceptionRow
from ..ids import exception_id
from .base import RuleContext, RuleResult

RULE_ID = "R07"


def _ratio(previous: float, current: float) -> float | None:
    """Scale-free magnitude change. Undefined when either side is zero, which is a real
    business state (no debt, no financing) rather than a scale change."""
    low, high = sorted((abs(previous), abs(current)))
    if low == 0:
        return None
    return high / low


def _compare(
    *, holding, metric: str, before, after, previous_period, current_period,
    mapping, low: float, high: float, severity: str,
) -> ExceptionRow | None:
    """Compare one metric across two quarters. Returns an exception only for an undeclared
    change of roughly 1,000x."""
    if mapping.declared_scale(previous_period.label) != mapping.declared_scale(current_period.label):
        return None  # the restatement is declared in the mapping

    ratio = _ratio(before.value, after.value)
    if ratio is None or not (low <= ratio <= high):
        return None

    declared = mapping.declared_scale(current_period.label)
    direction = "smaller" if abs(after.value) < abs(before.value) else "larger"
    return ExceptionRow(
        exception_id=exception_id(current_period.label, holding.holding_id, RULE_ID, metric),
        rule_id=RULE_ID,
        severity=severity,
        holding_id=holding.holding_id,
        period_label=current_period.label,
        period_end=current_period.period_end,
        subject=metric,
        evidence=(
            f"{metric} is {ratio:,.0f}x {direction} than {previous_period.label} "
            f"({before.value:,.1f} -> {after.value:,.1f}) while the mapping still "
            f"declares scale '{declared}'. Band flagged: {low:,.0f}x-{high:,.0f}x."
        ),
        expected=before.value,
        observed=after.value,
        difference=after.value - before.value,
        lineage_refs=(
            f"{before.lineage.source_file}"
            f"[{before.lineage.source_sheet or 'csv'}!{before.lineage.source_ref}]",
            f"{after.lineage.source_file}"
            f"[{after.lineage.source_sheet or 'csv'}!{after.lineage.source_ref}]",
        ),
    )


def evaluate(context: RuleContext) -> RuleResult:
    tolerance = context.config.rules.spec(RULE_ID).tolerance
    severity = context.config.rules.spec(RULE_ID).severity
    low, high = tolerance.low, tolerance.high
    if low is None or high is None:
        raise ValueError("R07 needs a ratio_band tolerance with low and high in rules.yaml")

    periods = list(context.config.fund.periods)
    exceptions: list[ExceptionRow] = []
    skipped: list[str] = []

    quarterly_usd = [
        row
        for row in context.canonical.metrics
        if row.unit == "USD" and row.frequency == "quarterly"
    ]

    for holding in context.config.fund.holdings:
        by_period = {
            (row.period_label, row.metric): row
            for row in quarterly_usd
            if row.holding_id == holding.holding_id
        }
        metrics = sorted({metric for _, metric in by_period})
        mapping = context.config.mapping_for(holding.template)
        for previous_period, current_period in zip(periods, periods[1:]):
            for metric in metrics:
                before = by_period.get((previous_period.label, metric))
                after = by_period.get((current_period.label, metric))
                if before is None or after is None:
                    skipped.append(
                        f"{RULE_ID} not evaluated for {holding.holding_id} {metric} "
                        f"{previous_period.label}->{current_period.label}: only one period present"
                    )
                    continue
                exception = _compare(
                    holding=holding, metric=metric, before=before, after=after,
                    previous_period=previous_period, current_period=current_period,
                    mapping=mapping, low=low, high=high, severity=severity,
                )
                if exception is not None:
                    exceptions.append(exception)

    return RuleResult(exceptions=tuple(exceptions), skipped=tuple(skipped))
