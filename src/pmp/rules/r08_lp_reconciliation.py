"""R08 - LP capital accounts have to add up to the fund.

The one rule here that is fund-level rather than holding-level, and the one an LP would
notice first. Expressed in SQL because it is a sum against a single filed total.
"""

from __future__ import annotations

from ..contract import FUND_ENTITY, ExceptionRow
from ..ids import exception_id
from .base import RuleContext, RuleResult, tolerance_value

RULE_ID = "R08"

QUERY = """
SELECT fs.period_label,
       fs.period_end,
       fs.total_called_usd              AS fund_called,
       lp.lp_called                     AS lp_called,
       lp.lp_count                      AS lp_count,
       fs.source_file                   AS fund_source,
       lp.lp_sources                    AS lp_sources
FROM fund_summary fs
LEFT JOIN (
    SELECT period_label,
           sum(called_usd)                     AS lp_called,
           count(*)                            AS lp_count,
           string_agg(DISTINCT source_file, ' | ') AS lp_sources
    FROM lp_capital
    GROUP BY period_label
) lp USING (period_label)
ORDER BY fs.period_label
"""


def evaluate(context: RuleContext) -> RuleResult:
    tolerance = tolerance_value(context, RULE_ID)
    severity = context.config.rules.spec(RULE_ID).severity
    exceptions: list[ExceptionRow] = []
    skipped: list[str] = []

    for row in context.connection.execute(QUERY).fetchall():
        period_label, period_end, fund_called, lp_called, lp_count, fund_source, lp_sources = row
        if lp_called is None:
            skipped.append(f"{RULE_ID} not evaluated for {period_label}: no LP capital rows loaded")
            continue
        difference = float(lp_called) - float(fund_called)
        if abs(difference) <= tolerance:
            continue
        exceptions.append(
            ExceptionRow(
                exception_id=exception_id(period_label, FUND_ENTITY, RULE_ID),
                rule_id=RULE_ID,
                severity=severity,
                holding_id=FUND_ENTITY,
                period_label=period_label,
                period_end=period_end,
                subject="total_called_usd",
                evidence=(
                    f"Sum of called capital across {lp_count} LPs is {lp_called:,.0f}, "
                    f"but the fund summary reports {fund_called:,.0f} "
                    f"(difference {difference:,.0f}, tolerance ±{tolerance:,.0f})."
                ),
                expected=float(fund_called),
                observed=float(lp_called),
                difference=difference,
                lineage_refs=(str(fund_source), str(lp_sources)),
            )
        )
    return RuleResult(exceptions=tuple(exceptions), skipped=tuple(skipped))
