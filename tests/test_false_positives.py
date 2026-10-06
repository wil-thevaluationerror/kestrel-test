"""Precision: the pipeline must stay quiet on clean data.

Q1 is clean for every holding. In Q2, five holdings carry one defect each and the fund
carries one; the remaining four holdings are clean in the same quarter, which is what makes
this test more than a smoke test.
"""

from pmp.pipeline import run

CLEAN_IN_Q2 = ("RE-C", "GE-C", "GV-B", "GV-C")
EXPECTED_Q2_RULES = {
    "RE-A": {"I02"},
    "RE-B": {"R07"},
    "GE-A": {"R03"},
    "GE-B": {"I01"},
    "GV-A": {"R04"},
    "FUND": {"R08"},
}


def test_q1_produces_no_exceptions_at_all(project):
    result = run(project)
    q1 = [e for e in result.queue.exceptions if e.period_label == "2026Q1"]
    assert q1 == []


def test_each_q2_holding_raises_only_its_own_defect(project):
    result = run(project)

    by_entity: dict[str, set[str]] = {}
    for exception in result.queue.exceptions:
        if exception.period_label != "2026Q2":
            continue
        by_entity.setdefault(exception.holding_id, set()).add(exception.rule_id)

    assert by_entity == EXPECTED_Q2_RULES


def test_the_clean_q2_holdings_raise_nothing(project):
    result = run(project)
    noisy = [
        e.exception_id for e in result.queue.exceptions if e.holding_id in CLEAN_IN_Q2
    ]
    assert noisy == []
