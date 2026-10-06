"""The rule interface.

Every rule is a pure function of canonical data: it reads, it never writes. A rule that
cannot be evaluated reports that fact rather than returning an empty list, because
"no exceptions" and "not checked" must never look the same on the summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import duckdb

from ..configio import ConfigBundle
from ..contract import ExceptionRow
from ..normalize import Canonical


@dataclass(frozen=True)
class RuleContext:
    canonical: Canonical
    config: ConfigBundle
    connection: duckdb.DuckDBPyConnection


@dataclass(frozen=True)
class RuleResult:
    exceptions: tuple[ExceptionRow, ...] = ()
    skipped: tuple[str, ...] = field(default=())


def tolerance_value(context: RuleContext, rule_id: str) -> float:
    tolerance = context.config.rules.spec(rule_id).tolerance
    if tolerance.value is None:
        raise ValueError(f"rule {rule_id} has no scalar tolerance in config/rules.yaml")
    return tolerance.value
