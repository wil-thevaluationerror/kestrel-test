"""R08: the sum of LP called capital must equal the fund's filed called capital."""

from pmp.normalize import Canonical
from pmp.rules import r08_lp_reconciliation

from .helpers import fund_row, lp_row, rule_context


def test_lp_schedule_that_ties_raises_nothing(config, tmp_path):
    canonical = Canonical(
        lp_capital=(lp_row("LP-001", "2026Q2", 600_000), lp_row("LP-002", "2026Q2", 400_000)),
        fund_summary=(fund_row("2026Q2", 1_000_000),),
    )

    assert r08_lp_reconciliation.evaluate(rule_context(canonical, config, tmp_path)).exceptions == ()


def test_understated_lp_row_raises_a_fund_level_exception(config, tmp_path):
    # Arrange: defect D10 - one LP's called capital is short by 312,500.
    canonical = Canonical(
        lp_capital=(lp_row("LP-001", "2026Q2", 600_000), lp_row("LP-017", "2026Q2", 87_500)),
        fund_summary=(fund_row("2026Q2", 1_000_000),),
    )

    result = r08_lp_reconciliation.evaluate(rule_context(canonical, config, tmp_path))

    assert [e.exception_id for e in result.exceptions] == ["EX-2026Q2-FUND-R08"]
    assert result.exceptions[0].difference == -312_500
    assert result.exceptions[0].holding_id == "FUND"


def test_a_period_with_no_lp_rows_is_reported_as_not_evaluated(config, tmp_path):
    canonical = Canonical(fund_summary=(fund_row("2026Q2", 1_000_000),))

    result = r08_lp_reconciliation.evaluate(rule_context(canonical, config, tmp_path))

    assert result.exceptions == ()
    assert any("no LP capital rows loaded" in note for note in result.skipped)
