"""Tabs and emphasis: presentation is config, and no holding may fall off the page."""

import re

import pytest

from pmp.configio import load_config
from pmp.pipeline import run


def test_every_asset_class_in_the_fund_has_a_tab(config):
    classes = {holding.asset_class for holding in config.fund.holdings}
    assert classes <= set(config.presentation.asset_classes)


def test_a_holding_in_an_asset_class_with_no_tab_is_rejected_at_load(mutable_project):
    """Otherwise the holding would simply not be rendered, which is the failure mode this
    project exists to argue against."""
    fund = mutable_project.config / "fund.yaml"
    fund.write_text(fund.read_text().replace("asset_class: growth_venture", "asset_class: credit", 1))

    with pytest.raises(ValueError, match="no entry in config/presentation.yaml"):
        load_config(mutable_project)


def test_a_headline_metric_that_does_not_exist_is_rejected_at_load(mutable_project):
    presentation = mutable_project.config / "presentation.yaml"
    presentation.write_text(presentation.read_text().replace("headline_metric: noi", "headline_metric: ebit"))

    with pytest.raises(ValueError, match="not defined for asset class 'real_estate'"):
        load_config(mutable_project)


def test_rising_costs_read_as_bad_and_falling_debt_as_good(config):
    """Colour has to mean something, or it is worse than no colour."""
    real_estate = config.presentation.asset_classes["real_estate"]

    assert real_estate.sentiment_for("opex", 4.7) == "bad"
    assert real_estate.sentiment_for("debt_balance", -0.5) == "good"
    assert real_estate.sentiment_for("noi", 2.6) == "good"
    assert real_estate.sentiment_for("revenue", None) == "neutral"


def test_cash_flow_lines_are_left_uncoloured(config):
    """A large investing outflow can be a good quarter; the page should not claim otherwise."""
    equity = config.presentation.asset_classes["growth_equity"]

    assert equity.sentiment_for("cash_flow_investing", -34.0) == "neutral"
    assert equity.sentiment_for("cash_flow_operating", 205.8) == "neutral"


def test_every_holding_appears_in_exactly_one_tab(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)
    config = load_config(project)

    placed = [
        panel.holding_id for section in result.summary.sections for panel in section.panels
    ]
    assert sorted(placed) == sorted(h.holding_id for h in config.fund.holdings)
    assert len(placed) == len(set(placed))


def test_each_tab_has_an_overview_and_each_card_a_headline(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)

    for section in result.summary.sections:
        assert section.stats, f"{section.asset_class} has no overview figures"
        assert section.invested is not None
        for panel in section.panels:
            assert panel.headline is not None, f"{panel.holding_id} leads with nothing"


def test_the_markup_wires_each_tab_to_its_panel(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)
    html = (result.outputs_dir / "summary.html").read_text()

    # Counted on the wiring attributes rather than the role, because the script and the
    # print styles mention the roles too.
    assert html.count('aria-controls="panel-') == len(result.summary.sections)
    assert html.count('aria-labelledby="tab-') == len(result.summary.sections)
    for section in result.summary.sections:
        assert f'id="tab-{section.asset_class}"' in html
        assert f'aria-controls="panel-{section.asset_class}"' in html
        assert f'id="panel-{section.asset_class}"' in html
        assert f'aria-labelledby="tab-{section.asset_class}"' in html


def test_without_javascript_the_page_is_one_readable_document(project, demo_resolutions):
    """The tablist ships hidden and no panel is hidden in the markup, so a reader with no
    scripting - or a printer - gets every asset class."""
    result = run(project, resolutions_path=demo_resolutions)
    html = (result.outputs_dir / "summary.html").read_text()

    body = html.split("<main>")[1].split("</main>")[0]

    assert 'id="asset-tabs" hidden' in html, "the tablist must ship hidden"
    panels = re.findall(r"<section class=\"asset-class\"[^>]*>", body)
    assert len(panels) == len(result.summary.sections)
    assert not any("hidden" in panel for panel in panels), "no panel may be hidden in markup"
    assert '[role="tabpanel"][hidden] { display: block !important; }' in html


def test_a_correction_is_counted_on_its_tab_and_its_card(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)

    by_class = {s.asset_class: s for s in result.summary.sections}
    # RE-B carries the four thousands restatements; GE-A and GE-B one correction each.
    assert by_class["real_estate"].corrections == 4
    assert by_class["growth_equity"].corrections == 2
    assert by_class["growth_venture"].corrections == 0

    re_b = [p for p in by_class["real_estate"].panels if p.holding_id == "RE-B"][0]
    assert re_b.corrections == 4
