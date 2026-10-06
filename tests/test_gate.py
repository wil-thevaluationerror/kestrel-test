"""The gate: an open blocking exception must stop the fund report."""

from pmp.pipeline import run


def test_no_summary_is_written_while_a_blocking_exception_is_open(project):
    result = run(project)

    assert result.gate.passed is False
    assert not (result.outputs_dir / "summary.html").exists()
    assert result.summary is None


def test_the_audit_trail_is_still_written_when_the_gate_holds(project):
    """A held run is a result too, and has to be reviewable."""
    result = run(project)

    assert (result.outputs_dir / "exceptions.csv").exists()
    assert (result.outputs_dir / "manifest.json").exists()


def test_the_gate_names_every_blocking_exception(project):
    result = run(project)

    blocking_ids = [e.exception_id for e in result.gate.blocking]
    assert len(blocking_ids) == 9
    assert result.manifest["gate"]["blocking_exception_ids"] == blocking_ids
    message = result.gate.message()
    for exception_id in blocking_ids:
        assert exception_id in message


def test_a_warning_alone_does_not_hold_the_gate(project, mutable_project):
    """Warn means visible, not blocking - otherwise reviewers learn to override the gate."""
    resolutions = mutable_project.config / "stale.yaml"
    resolutions.write_text(
        "resolutions:\n"
        "  - exception_id: EX-2026Q2-GV-Z-R04\n"
        "    decision: accept\n"
        "    reviewer: W. Butler-Croutwater\n"
        "    date: 2026-10-06\n"
        "    rationale: 'Carried over from a prior quarter and no longer applicable.'\n"
    )
    # The fixture's own blocking exceptions still exist, so check the stale row's severity only.
    result = run(mutable_project, resolutions_path=resolutions)
    stale = [e for e in result.queue.exceptions if e.rule_id == "RES-STALE"]

    assert len(stale) == 1
    assert stale[0].severity == "warn"
    assert stale[0] not in result.gate.blocking
