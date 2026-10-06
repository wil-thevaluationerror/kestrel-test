"""R03 - the cash bridge has to tie.

Beginning cash plus the three flow lines must equal ending cash. This is the cheapest check
that catches a company omitting a payment from its bridge, which is how D04 is built.
"""

from __future__ import annotations

from ..contract import ExceptionRow
from ..ids import exception_id
from .base import RuleContext, RuleResult, tolerance_value

RULE_ID = "R03"
FLOW_METRICS = ("cash_flow_operating", "cash_flow_investing", "cash_flow_financing")
REQUIRED = ("cash_begin", *FLOW_METRICS, "cash_end")


def evaluate(context: RuleContext) -> RuleResult:
    tolerance = tolerance_value(context, RULE_ID)
    severity = context.config.rules.spec(RULE_ID).severity
    exceptions: list[ExceptionRow] = []
    skipped: list[str] = []

    for holding in context.config.fund.holdings:
        if holding.asset_class != "growth_equity":
            continue
        for period in context.config.fund.periods:
            values = {
                row.metric: row
                for row in context.canonical.metrics
                if row.holding_id == holding.holding_id
                and row.period_label == period.label
                and row.metric in REQUIRED
            }
            missing = [m for m in REQUIRED if m not in values]
            if missing:
                skipped.append(
                    f"{RULE_ID} not evaluated for {holding.holding_id} {period.label}: "
                    f"missing {', '.join(missing)}"
                )
                continue

            computed = values["cash_begin"].value + sum(values[m].value for m in FLOW_METRICS)
            reported = values["cash_end"].value
            difference = computed - reported
            if abs(difference) <= tolerance:
                continue

            exceptions.append(
                ExceptionRow(
                    exception_id=exception_id(period.label, holding.holding_id, RULE_ID),
                    rule_id=RULE_ID,
                    severity=severity,
                    holding_id=holding.holding_id,
                    period_label=period.label,
                    period_end=period.period_end,
                    subject="cash_end",
                    evidence=(
                        f"Bridge does not tie: beginning cash {values['cash_begin'].value:,.0f} "
                        f"+ operating {values['cash_flow_operating'].value:,.0f} "
                        f"+ investing {values['cash_flow_investing'].value:,.0f} "
                        f"+ financing {values['cash_flow_financing'].value:,.0f} "
                        f"= {computed:,.0f}, but ending cash is reported as {reported:,.0f} "
                        f"(difference {difference:,.0f}, tolerance ±{tolerance:,.0f})."
                    ),
                    expected=computed,
                    observed=reported,
                    difference=difference,
                    lineage_refs=tuple(
                        f"{values[m].lineage.source_file}"
                        f"[{values[m].lineage.source_sheet or 'csv'}!{values[m].lineage.source_ref}]"
                        for m in REQUIRED
                    ),
                )
            )
    return RuleResult(exceptions=tuple(exceptions), skipped=tuple(skipped))
