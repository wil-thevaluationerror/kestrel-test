"""Config is the control surface: tolerances, severities, and sign-off rules live in YAML.

If any of these could only be changed in code, a reviewer could not audit them.
"""

import pytest
from pydantic import ValidationError

from pmp.configio import load_config
from pmp.contract import Resolution
from pmp.pipeline import run


def test_widening_a_tolerance_in_config_changes_the_outcome(mutable_project):
    before = run(mutable_project)
    assert any(e.rule_id == "R03" for e in before.queue.exceptions)

    rules = mutable_project.config / "rules.yaml"
    rules.write_text(
        rules.read_text().replace(
            '    description: "Beginning cash + operating + investing + financing flows = ending cash."\n'
            "    tolerance: {kind: absolute_usd, value: 1.0}",
            '    description: "Beginning cash + operating + investing + financing flows = ending cash."\n'
            "    tolerance: {kind: absolute_usd, value: 100000.0}",
        )
    )

    after = run(mutable_project)
    assert not any(e.rule_id == "R03" for e in after.queue.exceptions)


def test_disabling_a_rule_is_reported_rather_than_hidden(project):
    result = run(project)

    assert set(result.manifest["rules_disabled"]) == {"R01", "R02", "R05", "R06"}
    assert any("R02 (Completeness) is disabled" in note
               for note in result.manifest["checks_not_evaluated"])


def test_a_tolerance_change_also_changes_the_config_hash_in_the_manifest(mutable_project):
    before = run(mutable_project).manifest["config_hashes"]["config/rules.yaml"]

    rules = mutable_project.config / "rules.yaml"
    rules.write_text(rules.read_text() + "\n# reviewed 2026-10-06\n")

    after = run(mutable_project).manifest["config_hashes"]["config/rules.yaml"]
    assert before != after


def test_a_resolution_without_a_real_rationale_is_rejected():
    """A sign-off with no reasoning is not a sign-off."""
    with pytest.raises(ValidationError, match="real sentence"):
        Resolution.model_validate(
            {
                "exception_id": "EX-2026Q2-GE-A-R03",
                "decision": "accept",
                "reviewer": "W. Butler-Croutwater",
                "date": "2026-10-06",
                "rationale": "fine",
            }
        )


def test_two_decisions_on_one_exception_are_rejected(mutable_project):
    resolutions = mutable_project.config / "double.yaml"
    entry = (
        "  - exception_id: EX-2026Q2-RE-A-I02\n"
        "    decision: accept\n"
        "    reviewer: W. Butler-Croutwater\n"
        "    date: 2026-10-06\n"
        "    rationale: 'Duplicate submission, original retained for the record.'\n"
    )
    resolutions.write_text("resolutions:\n" + entry + entry)

    with pytest.raises(ValueError, match="one decision per exception"):
        load_config(mutable_project, resolutions_path=resolutions)
