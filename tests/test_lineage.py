"""Lineage: every number on the summary must resolve to a source cell or a resolution record.

The trace is only worth having if a reviewer can open it, so these tests check the whole
chain: the figure carries an origin, the origin names a real file at a recorded hash, the
cited cell exists in the preview embedded in the report, and the file can be downloaded
from next to the report.
"""

from pmp.hashing import sha256_file
from pmp.pipeline import run
from pmp.report import CONFIG_FILE
from pmp.sources import SOURCES_DIRNAME


def _summary(project, demo_resolutions):
    result = run(project, resolutions_path=demo_resolutions)
    assert result.summary is not None
    return result


def _all_traces(summary):
    return [trace for traced in summary.traced_values for trace in traced.traces]


def test_every_reported_value_carries_at_least_one_trace(project, demo_resolutions):
    result = _summary(project, demo_resolutions)

    assert result.summary.traced_values
    for traced in result.summary.traced_values:
        assert traced.traces, f"a reported {traced.unit} value has no trace"
        for trace in traced.traces:
            assert trace.kind in {"cell", "resolution", "config"}
            assert trace.file and trace.ref


def test_every_trace_points_at_a_file_that_exists_with_the_recorded_hash(project, demo_resolutions):
    result = _summary(project, demo_resolutions)

    for trace in _all_traces(result.summary):
        path = project.root / trace.file
        assert path.exists(), f"trace points at a missing file: {trace.label}"
        assert sha256_file(path) == trace.sha256, f"stale hash in {trace.label}"


def test_every_cell_trace_resolves_to_a_cell_in_the_embedded_preview(project, demo_resolutions):
    """This is the trace actually working: the cited reference exists in the document shown."""
    result = _summary(project, demo_resolutions)
    files = result.summary.source_index["files"]

    for trace in _all_traces(result.summary):
        if trace.kind != "cell":
            continue
        document = files.get(trace.file)
        assert document, f"no preview was embedded for {trace.file}"
        sheets = [s for s in document["sheets"] if trace.sheet in (None, s["name"])]
        assert sheets, f"{trace.file} has no sheet named {trace.sheet!r}"
        refs = {
            cell["ref"]
            for sheet in sheets
            for row in sheet["rows"]
            for cell in row
            if cell["ref"]
        }
        assert trace.ref in refs, f"cell {trace.ref} is not in the preview of {trace.file}"


def test_every_resolution_trace_resolves_to_its_decision_record(project, demo_resolutions):
    result = _summary(project, demo_resolutions)
    records = result.summary.source_index["resolutions"]

    resolution_traces = [t for t in _all_traces(result.summary) if t.kind == "resolution"]
    assert resolution_traces, "the demo resolutions should put decisions on the page"
    for trace in resolution_traces:
        record = records.get(trace.exception_id)
        assert record, f"no decision record embedded for {trace.exception_id}"
        assert trace.exception_id in record["yaml"]
        assert record["reviewer"] and record["decision"]


def test_every_traced_document_is_downloadable_next_to_the_report(project, demo_resolutions):
    result = _summary(project, demo_resolutions)
    files = result.summary.source_index["files"]

    for trace in _all_traces(result.summary):
        document = files[trace.file]
        assert document["download"], f"no source copy offered for {trace.file}"
        copy = result.outputs_dir / document["download"]
        assert copy.exists(), f"download link points at a missing copy: {document['download']}"
        assert sha256_file(copy) == trace.sha256, f"source copy of {trace.file} does not match"


def test_an_overridden_value_traces_to_both_the_filed_cell_and_the_decision(project, demo_resolutions):
    result = _summary(project, demo_resolutions)

    overridden = [t for t in result.summary.traced_values if t.overridden]
    assert overridden, "the demo resolutions should put at least one override on the page"
    for traced in overridden:
        assert any(t.kind == "resolution" for t in traced.traces)
        assert "EX-" in traced.override_note


def test_the_rendered_page_offers_a_trace_control_for_every_figure(project, demo_resolutions):
    """Guards the template as well as the model: a dropped marker would be caught here."""
    result = _summary(project, demo_resolutions)
    html = (result.outputs_dir / "summary.html").read_text()

    metric_figures = sum(
        1
        for section in result.summary.sections
        for panel in section.panels
        for line in panel.lines
        if line.current.value is not None
    )
    invested_per_holding = sum(len(section.panels) for section in result.summary.sections)
    section_aggregates = sum(len(section.stats) for section in result.summary.sections)
    section_invested = sum(1 for section in result.summary.sections if section.invested)
    fund_figures = 2  # commitments and called to date

    expected = (
        metric_figures
        + invested_per_holding
        + section_aggregates
        + section_invested
        + fund_figures
    )
    assert html.count('class="trace"') == expected


def test_the_fund_level_figures_trace_to_the_filed_fund_summary(project, demo_resolutions):
    result = _summary(project, demo_resolutions)

    for traced in (result.summary.fund_panel.commitments, result.summary.fund_panel.called):
        assert any("fund-summary" in trace.file for trace in traced.traces)


def test_invested_capital_traces_to_the_fund_config_not_a_source_report(project, demo_resolutions):
    """It is not a reported figure, and the summary should not pretend otherwise."""
    result = _summary(project, demo_resolutions)

    panel = result.summary.sections[0].panels[0]
    trace = panel.invested_capital.traces[0]
    assert trace.kind == "config"
    assert trace.file == CONFIG_FILE


def test_the_source_pack_sits_under_the_run_directory(project, demo_resolutions):
    result = _summary(project, demo_resolutions)

    pack = result.outputs_dir / SOURCES_DIRNAME
    assert pack.is_dir()
    assert len(list(pack.iterdir())) == len(result.sources.documents)
