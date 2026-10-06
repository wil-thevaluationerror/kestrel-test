"""R03: beginning cash plus flows must equal ending cash."""

from pmp.normalize import Canonical
from pmp.rules import r03_cash_bridge

from .helpers import cash_bridge, rule_context


def test_bridge_that_ties_raises_nothing(config, tmp_path):
    # Arrange: GE-A is a growth equity holding, so R03 applies to it.
    canonical = Canonical(metrics=tuple(cash_bridge("GE-A", "2026Q2", 10_000_000, 500_000, -200_000, 0, 10_300_000)))

    # Act
    result = r03_cash_bridge.evaluate(rule_context(canonical, config, tmp_path))

    # Assert
    assert result.exceptions == ()


def test_bridge_off_by_more_than_tolerance_raises_one_exception(config, tmp_path):
    # Arrange: investing outflow understated by 48,200, as in defect D04.
    canonical = Canonical(metrics=tuple(cash_bridge("GE-A", "2026Q2", 10_000_000, 500_000, -200_000, 0, 10_251_800)))

    result = r03_cash_bridge.evaluate(rule_context(canonical, config, tmp_path))

    assert [e.rule_id for e in result.exceptions] == ["R03"]
    exception = result.exceptions[0]
    assert exception.holding_id == "GE-A"
    assert exception.difference == 48_200
    assert exception.severity == "block"
    assert "48,200" in exception.evidence


def test_rounding_inside_tolerance_is_not_an_exception(config, tmp_path):
    # Arrange: 50 cents out, inside the ±$1 tolerance in config/rules.yaml.
    canonical = Canonical(metrics=tuple(cash_bridge("GE-A", "2026Q2", 10_000_000, 500_000, -200_000, 0, 10_300_000.5)))

    assert r03_cash_bridge.evaluate(rule_context(canonical, config, tmp_path)).exceptions == ()


def test_incomplete_bridge_is_reported_as_not_evaluated(config, tmp_path):
    """A missing component must not look the same as a clean bridge."""
    rows = cash_bridge("GE-A", "2026Q2", 10_000_000, 500_000, -200_000, 0, 10_300_000)
    canonical = Canonical(metrics=tuple(r for r in rows if r.metric != "cash_end"))

    result = r03_cash_bridge.evaluate(rule_context(canonical, config, tmp_path))

    assert result.exceptions == ()
    assert any("missing cash_end" in note for note in result.skipped)
