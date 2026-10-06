"""Canonical tables in DuckDB, and the staged Parquet layer underneath them.

DuckDB is here because the reconciliation checks are naturally set-based (sum LP capital,
sum ownership by holding) and because a single file warehouse needs no server to review.
Lineage columns are flattened onto every table so a number and its provenance are always
one row apart.
"""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import duckdb
import pandas as pd

from .contract import CapTableRow, ExceptionRow, FundSummaryRow, LPCapitalRow, MetricRow
from .ingest import StagedReport
from .normalize import Canonical
from .paths import Layout

LINEAGE_COLUMNS = (
    "source_file", "source_sheet", "source_ref", "file_sha256", "run_id",
    "mapping_version", "override_of", "override_source", "original_value",
)


def _columns_for(model) -> list[str]:
    """Column list for an empty table, so a quarter with no rows still has a typed shape."""
    return [name for name in model.model_fields if name != "lineage"] + list(LINEAGE_COLUMNS)


def _flatten(rows: tuple, model) -> pd.DataFrame:
    """One dict per contract row with lineage lifted into top-level columns."""
    records = []
    for row in rows:
        payload = row.model_dump()
        lineage = payload.pop("lineage", None) or {}
        for column in LINEAGE_COLUMNS:
            payload[column] = lineage.get(column)
        records.append(payload)
    if not records:
        return pd.DataFrame(columns=_columns_for(model))
    return pd.DataFrame.from_records(records)


def _register(connection: duckdb.DuckDBPyConnection, name: str, frame: pd.DataFrame) -> None:
    connection.register(f"_{name}", frame)
    connection.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _{name}")
    connection.unregister(f"_{name}")


def stage_parquet(reports: list[StagedReport], layout: Layout) -> list[Path]:
    """One Parquet file per source report: the audit copy of what the parser actually saw."""
    layout.staged.mkdir(parents=True, exist_ok=True)
    for existing in layout.staged.glob("*.parquet"):
        existing.unlink()

    written: list[Path] = []
    with duckdb.connect() as connection:
        for report in reports:
            frame = pd.DataFrame.from_records([asdict(row) for row in report.rows])
            target = layout.staged / f"{report.path.stem}.parquet"
            connection.register("staged_rows", frame)
            connection.execute(
                f"COPY (SELECT * FROM staged_rows) TO '{target.as_posix()}' (FORMAT PARQUET)"
            )
            connection.unregister("staged_rows")
            written.append(target)
    return sorted(written)


def build(
    canonical: Canonical, holdings_frame: pd.DataFrame, path: Path | None
) -> duckdb.DuckDBPyConnection:
    """Create the warehouse from scratch; a run is never a partial update.

    `path=None` builds in memory. The as-filed rule pass uses that so it can query canonical
    data without leaving a second warehouse behind: the file on disk must end the run holding
    the corrected data a reviewer would query.
    """
    if path is None:
        connection = duckdb.connect()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        connection = duckdb.connect(str(path))
    _register(connection, "holdings", holdings_frame)
    _register(connection, "metrics", _flatten(canonical.metrics, MetricRow))
    _register(connection, "cap_table", _flatten(canonical.cap_table, CapTableRow))
    _register(connection, "lp_capital", _flatten(canonical.lp_capital, LPCapitalRow))
    _register(connection, "fund_summary", _flatten(canonical.fund_summary, FundSummaryRow))
    return connection


def write_exceptions(connection: duckdb.DuckDBPyConnection, exceptions: list[ExceptionRow]) -> None:
    frame = pd.DataFrame.from_records([e.model_dump() for e in exceptions])
    if frame.empty:
        frame = pd.DataFrame(columns=list(ExceptionRow.model_fields))
    frame["lineage_refs"] = frame["lineage_refs"].apply(
        lambda refs: " | ".join(refs) if isinstance(refs, (list, tuple)) else refs
    )
    _register(connection, "exceptions", frame)
