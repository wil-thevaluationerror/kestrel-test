"""R04 - cap table ownership has to sum to 100%.

Set-based, so it is expressed in SQL against the warehouse rather than looped in Python.
"""

from __future__ import annotations

from ..contract import ExceptionRow
from ..ids import exception_id
from .base import RuleContext, RuleResult, tolerance_value

RULE_ID = "R04"
TARGET_PCT = 100.0

QUERY = """
SELECT holding_id,
       period_label,
       any_value(period_end)                      AS period_end,
       round(sum(ownership_pct), 6)               AS total_pct,
       count(*)                                   AS holder_count,
       string_agg(DISTINCT source_file, ' | ')    AS source_files
FROM cap_table
GROUP BY holding_id, period_label
ORDER BY holding_id, period_label
"""


def evaluate(context: RuleContext) -> RuleResult:
    tolerance = tolerance_value(context, RULE_ID)
    severity = context.config.rules.spec(RULE_ID).severity
    exceptions: list[ExceptionRow] = []

    for holding_id, period_label, period_end, total_pct, holder_count, sources in (
        context.connection.execute(QUERY).fetchall()
    ):
        difference = float(total_pct) - TARGET_PCT
        if abs(difference) <= tolerance:
            continue
        exceptions.append(
            ExceptionRow(
                exception_id=exception_id(period_label, holding_id, RULE_ID),
                rule_id=RULE_ID,
                severity=severity,
                holding_id=holding_id,
                period_label=period_label,
                period_end=period_end,
                subject="ownership_pct",
                evidence=(
                    f"Ownership across {holder_count} holders sums to {total_pct:.2f}%, "
                    f"expected {TARGET_PCT:.2f}% (difference {difference:+.2f} pp, "
                    f"tolerance ±{tolerance}pp)."
                ),
                expected=TARGET_PCT,
                observed=float(total_pct),
                difference=difference,
                lineage_refs=(sources,),
            )
        )
    return RuleResult(exceptions=tuple(exceptions))
