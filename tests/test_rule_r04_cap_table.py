"""R04: ownership across holders must sum to 100%."""

from pmp.normalize import Canonical
from pmp.rules import r04_cap_table

from .helpers import cap_row, rule_context


def test_cap_table_summing_to_100_raises_nothing(config, tmp_path):
    canonical = Canonical(
        cap_table=(
            cap_row("GV-A", "2026Q2", "Founders", 47.8),
            cap_row("GV-A", "2026Q2", "Series A Investors", 30.0),
            cap_row("GV-A", "2026Q2", "Employee Option Pool", 22.2),
        )
    )

    assert r04_cap_table.evaluate(rule_context(canonical, config, tmp_path)).exceptions == ()


def test_cap_table_summing_to_97_4_raises_a_blocking_exception(config, tmp_path):
    # Arrange: defect D01 - the founder row understates ownership by 2.6 points.
    canonical = Canonical(
        cap_table=(
            cap_row("GV-A", "2026Q2", "Founders", 45.2),
            cap_row("GV-A", "2026Q2", "Series A Investors", 30.0),
            cap_row("GV-A", "2026Q2", "Employee Option Pool", 22.2),
        )
    )

    result = r04_cap_table.evaluate(rule_context(canonical, config, tmp_path))

    assert [e.exception_id for e in result.exceptions] == ["EX-2026Q2-GV-A-R04"]
    assert result.exceptions[0].observed == 97.4
    assert result.exceptions[0].severity == "block"


def test_rounding_inside_tolerance_is_accepted(config, tmp_path):
    canonical = Canonical(
        cap_table=(
            cap_row("GV-A", "2026Q2", "Founders", 50.005),
            cap_row("GV-A", "2026Q2", "Series A Investors", 49.995),
        )
    )

    assert r04_cap_table.evaluate(rule_context(canonical, config, tmp_path)).exceptions == ()
