"""Ground truth: every seeded defect must be caught by the rule that is supposed to catch it.

The defect manifest is written by the generator before the pipeline runs, so this test
scores recall against a contract, not against whatever the pipeline happened to produce.
"""

from pmp.pipeline import run


def test_the_manifest_lists_the_defects_that_ship_in_v1(ground_truth):
    assert {d["id"] for d in ground_truth["defects"]} == {"D01", "D02", "D04", "D07", "D08", "D10"}


def test_every_seeded_defect_is_caught_by_its_expected_rule(project, ground_truth):
    result = run(project)
    raised = {
        (e.rule_id, e.holding_id, e.period_label) for e in result.queue.exceptions
    }

    missed = [
        defect for defect in ground_truth["defects"]
        if (defect["expected_rule"], defect["entity"], defect["period"]) not in raised
    ]
    assert missed == [], f"recall below 100%: {missed}"


def test_no_defect_slips_through_to_a_report(project):
    """Recall only matters if the gate acts on it."""
    result = run(project)

    assert result.gate.passed is False
    assert result.summary is None
