"""Corrections must answer a problem the as-filed data actually had.

A `correct` resolution is an instruction to overwrite a reported number. The only thing that
makes that safe is that a rule objected to the number first. These tests pin that down: an
override with no as-filed exception behind it must not reach canonical data, and a correction
that does not actually fix what it claims to fix must not clear the gate.
"""

import csv

import duckdb
import pytest
import yaml

from pmp import pipeline
from pmp.pipeline import run

SEEDED_EXCEPTION_IDS = {
    "EX-2026Q2-FUND-R08",
    "EX-2026Q2-GE-A-R03",
    "EX-2026Q2-GE-B-I01-NET-SALES",
    "EX-2026Q2-GV-A-R04",
    "EX-2026Q2-RE-A-I02",
    "EX-2026Q2-RE-B-R07-DEBT-BALANCE",
    "EX-2026Q2-RE-B-R07-NOI",
    "EX-2026Q2-RE-B-R07-OPEX",
    "EX-2026Q2-RE-B-R07-REVENUE",
}


def _write_resolutions(layout, name: str, body: str):
    path = layout.config / name
    path.write_text(body)
    return path


def _metric(result, holding_id: str, metric: str, period: str = "2026Q2"):
    rows = [
        row for row in result.canonical.metrics
        if row.holding_id == holding_id and row.metric == metric and row.period_label == period
    ]
    return rows[0] if rows else None


def _exceptions_csv(result) -> list[dict]:
    with (result.outputs_dir / "exceptions.csv").open(newline="") as handle:
        return list(csv.DictReader(handle))


# --------------------------------------------------------------- unanchored corrections

INVENTED = """resolutions:
  - exception_id: EX-2026Q2-GE-C-ANYTHING
    decision: correct
    target:
      table: metrics
      keys: {holding_id: GE-C, period_label: 2026Q2, metric: revenue, sub_period: 2026Q2}
      column: value
    corrected_value: 99999999
    source: "A conversation nobody can produce"
    reviewer: W. Butler-Croutwater
    date: 2026-10-06
    rationale: "Looked low to me, so I put in the number I was expecting to see."
"""


def test_a_correction_with_an_invented_exception_id_is_rejected(mutable_project):
    resolutions = _write_resolutions(mutable_project, "invented.yaml", INVENTED)

    result = run(mutable_project, resolutions_path=resolutions)

    unanchored = [e for e in result.queue.exceptions if e.rule_id == "RES-UNANCHORED"]
    assert len(unanchored) == 1
    assert "EX-2026Q2-GE-C-ANYTHING" in unanchored[0].evidence
    assert unanchored[0].severity == "block"
    for detail in ("W. Butler-Croutwater", "metrics", "GE-C", "revenue", "99999999"):
        assert detail in unanchored[0].evidence


def test_an_unanchored_correction_never_reaches_canonical_data(mutable_project):
    resolutions = _write_resolutions(mutable_project, "invented.yaml", INVENTED)

    result = run(mutable_project, resolutions_path=resolutions)

    revenue = _metric(result, "GE-C", "revenue")
    assert revenue is not None
    assert revenue.value != 99999999
    assert revenue.lineage.override_of is None


def test_an_unanchored_correction_holds_the_gate_and_writes_no_summary(mutable_project):
    resolutions = _write_resolutions(mutable_project, "invented.yaml", INVENTED)

    result = run(mutable_project, resolutions_path=resolutions)

    assert result.gate.passed is False
    assert not (result.outputs_dir / "summary.html").exists()
    assert any(e.rule_id == "RES-UNANCHORED" for e in result.gate.blocking)


TYPO_PERIOD = """resolutions:
  - exception_id: EX-2026Q3-GE-A-R03
    decision: correct
    target:
      table: metrics
      keys: {holding_id: GE-A, period_label: 2026Q2, metric: cash_flow_investing, sub_period: 2026Q2}
      column: value
    corrected_value: -462937
    source: "Email from Thornbury Analytics CFO, revised cash bridge v2"
    reviewer: W. Butler-Croutwater
    date: 2026-10-06
    rationale: "Right correction, wrong quarter in the exception reference."
"""


def test_a_typo_in_the_period_of_an_exception_id_is_rejected(mutable_project):
    """The correction is otherwise correct, which is exactly why it has to be caught."""
    resolutions = _write_resolutions(mutable_project, "typo.yaml", TYPO_PERIOD)

    result = run(mutable_project, resolutions_path=resolutions)

    unanchored = [e for e in result.queue.exceptions if e.rule_id == "RES-UNANCHORED"]
    assert [e.subject for e in unanchored] == ["EX-2026Q3-GE-A-R03"]
    assert result.gate.passed is False
    assert not (result.outputs_dir / "summary.html").exists()

    investing = _metric(result, "GE-A", "cash_flow_investing")
    assert investing.value == -414_737  # as filed
    assert investing.lineage.override_of is None


# ------------------------------------------------------- corrections that do not correct

WRONG_VALUE = """resolutions:
  - exception_id: EX-2026Q2-GE-A-R03
    decision: correct
    target:
      table: metrics
      keys: {holding_id: GE-A, period_label: 2026Q2, metric: cash_flow_investing, sub_period: 2026Q2}
      column: value
    corrected_value: -420000
    source: "Email from Thornbury Analytics CFO, revised cash bridge v2"
    reviewer: W. Butler-Croutwater
    date: 2026-10-06
    rationale: "Transcribed the revised investing line from the email by hand."
"""


def test_a_correction_that_does_not_clear_its_exception_leaves_it_open(mutable_project):
    """The bridge still does not tie after this correction, so R03 has not been answered."""
    resolutions = _write_resolutions(mutable_project, "wrong.yaml", WRONG_VALUE)

    result = run(mutable_project, resolutions_path=resolutions)

    bridge = [e for e in result.queue.exceptions if e.exception_id == "EX-2026Q2-GE-A-R03"]
    assert len(bridge) == 1
    assert bridge[0].status == "open"
    assert result.gate.passed is False
    assert any(e.exception_id == "EX-2026Q2-GE-A-R03" for e in result.gate.blocking)


# ------------------------------------------------------------------ the signed-off quarter


def test_the_demo_resolutions_resolve_every_seeded_exception(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)

    assert result.gate.passed is True
    rows = _exceptions_csv(result)
    by_id = {row["exception_id"]: row for row in rows}

    assert SEEDED_EXCEPTION_IDS <= set(by_id), (
        "the register must keep every exception the as-filed data raised: missing "
        f"{sorted(SEEDED_EXCEPTION_IDS - set(by_id))}"
    )
    for exception_id in SEEDED_EXCEPTION_IDS:
        assert by_id[exception_id]["status"].startswith("resolved:"), exception_id


def test_the_signed_off_quarter_raises_no_unanchored_corrections(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)

    assert [e for e in result.queue.exceptions if e.rule_id == "RES-UNANCHORED"] == []


def test_the_unmapped_label_correction_still_inserts_revenue_with_resolution_lineage(
    project, demo_resolutions
):
    """I01 is an ingestion exception: the value was never loaded, so there is nothing to
    update and the correction inserts it. That path must survive the anchoring change."""
    result = run(project, resolutions_path=demo_resolutions)

    revenue = _metric(result, "GE-B", "revenue")
    assert revenue is not None
    assert revenue.value == 7_853_000
    assert revenue.lineage.override_of == "EX-2026Q2-GE-B-I01-NET-SALES"
    assert revenue.lineage.original_value is None
    assert revenue.lineage.source_file.endswith("resolutions.demo.yaml")


def test_ingestion_exceptions_are_exempt_from_the_clearance_check(project, demo_resolutions):
    """A correction cannot make I01 or I02 stop firing - they describe what arrived, not a
    value a rule compared - so they must still be allowed to resolve."""
    result = run(project, resolutions_path=demo_resolutions)
    by_id = {e.exception_id: e for e in result.queue.exceptions}

    assert by_id["EX-2026Q2-GE-B-I01-NET-SALES"].status == "resolved:correct"
    assert by_id["EX-2026Q2-RE-A-I02"].status == "resolved:accept"


# ------------------------------------------------------------------------ ID stability


def test_exception_ids_do_not_change_between_the_two_passes(project, demo_resolutions):
    """Anchoring only works if an ID means the same thing before and after a correction."""
    as_filed = run(project).queue.exceptions
    corrected = run(project, resolutions_path=demo_resolutions).queue.exceptions

    as_filed_ids = {e.exception_id for e in as_filed}
    corrected_ids = {e.exception_id for e in corrected if not e.rule_id.startswith("RES-")}
    assert as_filed_ids == corrected_ids


def test_unanchored_correction_blocks_an_otherwise_resolved_run(mutable_project):
    demo = (mutable_project.config / "resolutions.demo.yaml").read_text()
    path = _write_resolutions(mutable_project, "extra.yaml", demo + INVENTED.split("resolutions:\n")[1])
    before = _metric(run(mutable_project), "GE-C", "revenue").value

    result = run(mutable_project, resolutions_path=path)

    assert [e.rule_id for e in result.gate.blocking] == ["RES-UNANCHORED"]
    assert not (result.outputs_dir / "summary.html").exists()
    assert _metric(result, "GE-C", "revenue").value == before
    assert not any(o.exception_id.endswith("ANYTHING") for o in result.overrides)


def test_register_preserves_filed_evidence_and_warehouse_is_corrected(project, demo_resolutions):
    filed = {e.exception_id: e for e in run(project).queue.exceptions}
    result = run(project, resolutions_path=demo_resolutions)

    assert len(result.queue.exceptions) == 9
    for exception in result.queue.exceptions:
        assert exception.evidence == filed[exception.exception_id].evidence
        assert exception.lineage_refs == filed[exception.exception_id].lineage_refs
    assert result.manifest["exception_counts"]["total"] == 9
    assert result.manifest["exception_counts"]["open"] == 0
    with duckdb.connect(str(project.warehouse), read_only=True) as connection:
        rows = connection.execute("SELECT exception_id, status FROM exceptions").fetchall()
        assert dict(rows) == {e.exception_id: e.status for e in result.queue.exceptions}
        value = connection.execute(
            "SELECT value FROM metrics WHERE holding_id = 'GE-A' "
            "AND period_label = '2026Q2' AND metric = 'cash_flow_investing'"
        ).fetchone()[0]
        assert value == -462_937


def test_verification_adds_new_exceptions_without_losing_filed_ones(mutable_project):
    """An ingestion correction can introduce a scale error that only verification sees."""
    demo = (mutable_project.config / "resolutions.demo.yaml").read_text()
    path = _write_resolutions(mutable_project, "new-error.yaml", demo.replace("7853000", "7853"))

    result = run(mutable_project, resolutions_path=path)

    by_id = {e.exception_id: e for e in result.queue.exceptions}
    assert SEEDED_EXCEPTION_IDS <= set(by_id)
    assert by_id["EX-2026Q2-GE-B-R07-REVENUE"].status == "open"
    assert by_id["EX-2026Q2-GE-B-I01-NET-SALES"].status == "resolved:correct"
    assert result.gate.passed is False


@pytest.mark.parametrize("decision", ["accept", "exclude"])
def test_unknown_noncorrection_decisions_remain_warnings(mutable_project, decision):
    demo = yaml.safe_load((mutable_project.config / "resolutions.demo.yaml").read_text())
    demo["resolutions"].append({
        "exception_id": "EX-2026Q2-GE-C-ANYTHING", "decision": decision,
        "reviewer": "Test reviewer", "date": "2026-10-06",
        "rationale": "A stale decision retained for the warning check.",
    })
    path = _write_resolutions(mutable_project, "stale.yaml", yaml.safe_dump(demo))

    result = run(mutable_project, resolutions_path=path)

    assert result.gate.passed is True
    assert [(e.rule_id, e.severity) for e in result.queue.exceptions if e.status == "open"] == [
        ("RES-STALE", "warn")
    ]
    assert ("GE-C", "2026Q2") not in result.queue.excluded


def test_persisting_failures_have_identical_ids_in_both_rule_passes(mutable_project, monkeypatch):
    """Exercise actual rule results, since the retained register alone cannot prove ID stability."""
    demo = yaml.safe_load((mutable_project.config / "resolutions.demo.yaml").read_text())
    wrong_values = {
        "EX-2026Q2-GE-A-R03": -420_000,
        "EX-2026Q2-GV-A-R04": 46.0,
        "EX-2026Q2-RE-B-R07-REVENUE": 4000,
        "EX-2026Q2-FUND-R08": 2_000_000,
    }
    for resolution in demo["resolutions"]:
        if resolution["exception_id"] in wrong_values:
            resolution["corrected_value"] = wrong_values[resolution["exception_id"]]
    path = _write_resolutions(mutable_project, "still-wrong.yaml", yaml.safe_dump(demo))
    passes = []
    evaluate = pipeline.run_rules

    def capture(context):
        result = evaluate(context)
        passes.append(result)
        return result

    monkeypatch.setattr(pipeline, "run_rules", capture)
    result = run(mutable_project, resolutions_path=path)

    assert len(passes) == 2
    filed_ids = {e.exception_id for e in passes[0].exceptions}
    verification_ids = {e.exception_id for e in passes[1].exceptions}
    assert verification_ids == set(wrong_values)
    assert verification_ids <= filed_ids
    assert {e.exception_id for e in result.gate.blocking} == verification_ids
