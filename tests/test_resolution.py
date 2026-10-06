"""The human loop: after a reviewer signs off, the report builds and says what was decided."""

from pmp.hashing import sha256_file
from pmp.pipeline import run


def test_the_report_builds_once_every_blocking_exception_has_a_decision(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)

    assert result.gate.passed is True
    assert (result.outputs_dir / "summary.html").exists()


def test_every_applied_resolution_is_listed_on_the_summary(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)
    html = (result.outputs_dir / "summary.html").read_text()

    assert len(result.summary.resolutions) == 9
    for resolution in result.summary.resolutions:
        assert resolution.exception_id in html
        assert resolution.reviewer in html


def test_a_correction_keeps_the_filed_value_and_cites_a_source(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)

    bridge = [o for o in result.overrides if o.exception_id == "EX-2026Q2-GE-A-R03"][0]
    assert bridge.original_value == -414_737
    assert bridge.corrected_value == -462_937
    assert "revised cash bridge" in bridge.source

    corrected = [
        row for row in result.canonical.metrics
        if row.holding_id == "GE-A" and row.period_label == "2026Q2"
        and row.metric == "cash_flow_investing"
    ][0]
    assert corrected.value == -462_937
    assert corrected.lineage.override_of == "EX-2026Q2-GE-A-R03"
    assert corrected.lineage.original_value == -414_737


def test_a_resolution_never_edits_the_raw_file(project, demo_resolutions):
    before = {
        path: sha256_file(path) for path in sorted(project.raw.rglob("*")) if path.is_file()
    }

    run(project, resolutions_path=demo_resolutions)

    after = {
        path: sha256_file(path) for path in sorted(project.raw.rglob("*")) if path.is_file()
    }
    assert before == after


def test_a_resolution_for_an_exception_that_no_longer_fires_is_flagged(mutable_project):
    resolutions = mutable_project.config / "stale.yaml"
    resolutions.write_text(
        "resolutions:\n"
        "  - exception_id: EX-2026Q1-RE-A-R03\n"
        "    decision: accept\n"
        "    reviewer: W. Butler-Croutwater\n"
        "    date: 2026-10-06\n"
        "    rationale: 'Signed off last quarter and never removed from the file.'\n"
    )

    result = run(mutable_project, resolutions_path=resolutions)

    stale = [e for e in result.queue.exceptions if e.rule_id == "RES-STALE"]
    assert len(stale) == 1
    assert "EX-2026Q1-RE-A-R03" in stale[0].evidence


def test_an_exclusion_holds_the_holding_out_of_the_summary(mutable_project, demo_resolutions):
    """Exclusion must remove the holding from the page, not just clear the exception."""
    text = demo_resolutions.read_text().replace(
        """  - exception_id: EX-2026Q2-GV-A-R04
    decision: correct
    target:
      table: cap_table
      keys: {holding_id: GV-A, period_label: 2026Q2, holder: Founders}
      column: ownership_pct
    corrected_value: 47.8""",
        """  - exception_id: EX-2026Q2-GV-A-R04
    decision: exclude""",
    )
    resolutions = mutable_project.config / "exclude.yaml"
    resolutions.write_text(text)

    result = run(mutable_project, resolutions_path=resolutions)

    assert result.gate.passed is True
    assert ("GV-A", "2026Q2") in result.queue.excluded
    panels = [
        panel.holding_id
        for section in result.summary.sections
        for panel in section.panels
    ]
    assert "GV-A" not in panels
    assert any("GV-A" in note for note in result.summary.excluded)
