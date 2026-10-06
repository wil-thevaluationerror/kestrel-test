"""Builders for canonical rows, so a rule test reads as data in, exceptions out."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from pmp.configio import ConfigBundle
from pmp.contract import CapTableRow, FundSummaryRow, Lineage, LPCapitalRow, MetricRow
from pmp.normalize import Canonical
from pmp.rules.base import RuleContext
from pmp.warehouse import build

PERIOD_ENDS = {"2026Q1": date(2026, 3, 31), "2026Q2": date(2026, 6, 30)}


def lineage(ref: str = "B6", run_id: str = "run-test") -> Lineage:
    return Lineage(
        source_file="data/raw/test.xlsx",
        source_sheet="Sheet1",
        source_ref=ref,
        file_sha256="0" * 64,
        run_id=run_id,
        mapping_version="1.0.0",
    )


def metric(
    holding_id: str, period: str, name: str, value: float,
    unit: str = "USD", frequency: str = "quarterly", sub_period: str | None = None,
) -> MetricRow:
    return MetricRow(
        holding_id=holding_id,
        period_end=PERIOD_ENDS[period],
        period_label=period,
        metric=name,
        value=value,
        unit=unit,
        frequency=frequency,
        sub_period=sub_period or period,
        lineage=lineage(),
    )


def cap_row(holding_id: str, period: str, holder: str, pct: float, shares: float = 1000.0) -> CapTableRow:
    return CapTableRow(
        holding_id=holding_id,
        period_end=PERIOD_ENDS[period],
        period_label=period,
        holder=holder,
        share_class="Common",
        shares=shares,
        ownership_pct=pct,
        lineage=lineage(),
    )


def lp_row(lp_id: str, period: str, called: float, commitment: float = 1_000_000.0) -> LPCapitalRow:
    return LPCapitalRow(
        lp_id=lp_id,
        period_end=PERIOD_ENDS[period],
        period_label=period,
        commitment_usd=commitment,
        called_usd=called,
        distributed_usd=0.0,
        lineage=lineage(),
    )


def fund_row(period: str, called: float, commitments: float = 10_000_000.0) -> FundSummaryRow:
    return FundSummaryRow(
        period_end=PERIOD_ENDS[period],
        period_label=period,
        total_commitments_usd=commitments,
        total_called_usd=called,
        lineage=lineage(),
    )


def cash_bridge(holding_id: str, period: str, begin: float, op: float, inv: float,
                fin: float, end: float) -> list[MetricRow]:
    return [
        metric(holding_id, period, "cash_begin", begin),
        metric(holding_id, period, "cash_flow_operating", op),
        metric(holding_id, period, "cash_flow_investing", inv),
        metric(holding_id, period, "cash_flow_financing", fin),
        metric(holding_id, period, "cash_end", end),
    ]


def rule_context(canonical: Canonical, config: ConfigBundle, tmp_path: Path) -> RuleContext:
    connection = build(canonical, pd.DataFrame(columns=["holding_id"]), tmp_path / "w.duckdb")
    return RuleContext(canonical=canonical, config=config, connection=connection)
