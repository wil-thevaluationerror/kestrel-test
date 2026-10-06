"""R07: a USD metric that moves ~1,000x between quarters with no declared scale change."""

import pytest

from pmp.normalize import Canonical
from pmp.rules import r07_unit_scale

from .helpers import metric, rule_context


def test_normal_quarter_over_quarter_growth_raises_nothing(config, tmp_path):
    canonical = Canonical(
        metrics=(
            metric("RE-B", "2026Q1", "revenue", 3_715_000),
            metric("RE-B", "2026Q2", "revenue", 3_844_000),
        )
    )

    assert r07_unit_scale.evaluate(rule_context(canonical, config, tmp_path)).exceptions == ()


def test_thousandfold_drop_raises_a_blocking_exception(config, tmp_path):
    # Arrange: defect D08 - the Q2 pack was filed in thousands.
    canonical = Canonical(
        metrics=(
            metric("RE-B", "2026Q1", "revenue", 3_715_000),
            metric("RE-B", "2026Q2", "revenue", 3_844),
        )
    )

    result = r07_unit_scale.evaluate(rule_context(canonical, config, tmp_path))

    assert [e.exception_id for e in result.exceptions] == ["EX-2026Q2-RE-B-R07-REVENUE"]
    assert result.exceptions[0].severity == "block"
    assert "dollars" in result.exceptions[0].evidence


def test_a_declared_scale_change_suppresses_the_exception(mutable_project, tmp_path):
    """The mapping is the place to declare a restatement, and declaring it must silence R07."""
    from pmp.configio import load_config

    mapping = mutable_project.mappings / "real_estate.yaml"
    mapping.write_text(
        mapping.read_text().replace(
            "scale_overrides: []", "scale_overrides: [{period: 2026Q2, scale: thousands}]"
        )
    )
    config = load_config(mutable_project)
    canonical = Canonical(
        metrics=(
            metric("RE-B", "2026Q1", "revenue", 3_715_000),
            metric("RE-B", "2026Q2", "revenue", 3_844),
        )
    )

    assert r07_unit_scale.evaluate(rule_context(canonical, config, tmp_path)).exceptions == ()


def test_a_zero_prior_value_is_not_treated_as_a_scale_change(config, tmp_path):
    """No debt last quarter and debt this quarter is a business event, not a unit change."""
    canonical = Canonical(
        metrics=(
            metric("RE-B", "2026Q1", "debt_balance", 0),
            metric("RE-B", "2026Q2", "debt_balance", 5_000_000),
        )
    )

    assert r07_unit_scale.evaluate(rule_context(canonical, config, tmp_path)).exceptions == ()


@pytest.mark.parametrize("ratio", [400, 3000])
def test_moves_outside_the_configured_band_are_left_to_other_rules(config, tmp_path, ratio):
    canonical = Canonical(
        metrics=(
            metric("RE-B", "2026Q1", "revenue", 1_000_000 * ratio),
            metric("RE-B", "2026Q2", "revenue", 1_000_000),
        )
    )

    assert r07_unit_scale.evaluate(rule_context(canonical, config, tmp_path)).exceptions == ()
