"""Which rules run, in which order.

Disabled rules are listed here too, so the run manifest can say what was not checked
instead of leaving a reviewer to assume full coverage.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from ..contract import ExceptionRow
from . import r03_cash_bridge, r04_cap_table, r07_unit_scale, r08_lp_reconciliation
from .base import RuleContext, RuleResult

Evaluator = Callable[[RuleContext], RuleResult]

CANONICAL_RULES: dict[str, Evaluator] = {
    r03_cash_bridge.RULE_ID: r03_cash_bridge.evaluate,
    r04_cap_table.RULE_ID: r04_cap_table.evaluate,
    r07_unit_scale.RULE_ID: r07_unit_scale.evaluate,
    r08_lp_reconciliation.RULE_ID: r08_lp_reconciliation.evaluate,
}

# Ingestion checks raise their exceptions during ingest/normalize, not here.
INGESTION_RULES = ("I01", "I02")


@dataclass(frozen=True)
class RuleRunResult:
    exceptions: tuple[ExceptionRow, ...]
    skipped: tuple[str, ...]
    rules_run: tuple[str, ...]
    rules_disabled: tuple[str, ...]


def run_rules(context: RuleContext) -> RuleRunResult:
    exceptions: list[ExceptionRow] = []
    skipped: list[str] = []
    ran: list[str] = []

    for rule_id, evaluate in CANONICAL_RULES.items():
        if not context.config.rules.is_enabled(rule_id):
            continue
        result = evaluate(context)
        exceptions.extend(result.exceptions)
        skipped.extend(result.skipped)
        ran.append(rule_id)

    disabled = tuple(
        rule_id
        for rule_id, spec in context.config.rules.rules.items()
        if not spec.enabled
    )
    return RuleRunResult(
        exceptions=tuple(sorted(exceptions, key=lambda e: e.exception_id)),
        skipped=tuple(sorted(skipped)),
        rules_run=tuple(sorted(ran) + sorted(INGESTION_RULES)),
        rules_disabled=disabled,
    )
