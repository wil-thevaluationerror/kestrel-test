"""The source pack: a trace is only useful if the reviewer can open the document behind it."""

import pytest

from pmp.ingest import ingest
from pmp.configio import load_config
from pmp.hashing import sha256_file
from pmp.pipeline import run
from pmp.sources import SOURCES_DIRNAME, collect, read_document


def test_a_workbook_preview_is_keyed_by_the_same_cell_refs_as_the_lineage(project):
    path = sorted(project.raw.glob("2026Q2/**/RE-B_*.xlsx"))[0]

    document = read_document(path, project.root)

    sheet = document.sheets[0]
    assert sheet.name == "Operating Summary"
    cells = {cell.ref: cell.text for row in sheet.rows for cell in row if cell.ref}
    assert cells["A6"] == "Rental Revenue"
    assert cells["B6"] == "3844"  # as filed, in thousands - the preview does not restate


def test_a_csv_preview_is_keyed_by_row_and_column_like_its_lineage(project):
    path = sorted(project.raw.glob("2026Q2/**/GV-A_*cap-table.csv"))[0]

    document = read_document(path, project.root)

    cells = {cell.ref: cell.text for row in document.sheets[0].rows for cell in row if cell.ref}
    assert cells["row 2:holder"] == "Founders"
    assert cells["row 2:ownership_pct"] == "45.2"


def test_collected_copies_are_byte_identical_to_the_originals(project, tmp_path):
    config = load_config(project)
    reports, _ = ingest(project, config.fund)
    paths = [report.path for report in reports]

    bundle = collect(paths, project.root, tmp_path, copy_files=True)

    assert len(bundle.documents) == len(paths)
    for path in paths:
        document = bundle.get(str(path.relative_to(project.root)))
        copy = tmp_path / document.download
        assert copy.read_bytes() == path.read_bytes()
        assert document.sha256 == sha256_file(copy)


def test_files_sharing_a_name_never_overwrite_each_other_in_the_pack(project, tmp_path):
    """The pack is flat, so two documents with one basename must still both survive."""
    first = sorted(project.raw.glob("2026Q1/**/RE-A_*.xlsx"))[0]
    other = sorted(project.raw.glob("2026Q2/**/RE-B_*.xlsx"))[0]
    clash = tmp_path / "elsewhere" / first.name
    clash.parent.mkdir(parents=True)
    clash.write_bytes(other.read_bytes())

    bundle = collect([first, clash], tmp_path, tmp_path / "out", copy_files=True)

    downloads = {document.download for document in bundle.documents.values()}
    assert len(downloads) == 2
    for document in bundle.documents.values():
        assert (tmp_path / "out" / document.download).exists()


def test_the_pack_is_written_under_the_run_directory_and_recorded_in_the_manifest(
    project, demo_resolutions
):
    result = run(project, resolutions_path=demo_resolutions)

    pack = result.outputs_dir / SOURCES_DIRNAME
    assert pack.is_dir()
    assert len(result.manifest["source_copies"]) == len(result.sources.documents)
    for path, record in result.manifest["source_copies"].items():
        assert sha256_file(result.outputs_dir / record["download"]) == record["sha256"]
        assert sha256_file(project.root / path) == record["sha256"]


def test_copying_sources_never_touches_the_originals(project, demo_resolutions):
    before = {p: sha256_file(p) for p in sorted(project.raw.rglob("*")) if p.is_file()}

    run(project, resolutions_path=demo_resolutions)

    after = {p: sha256_file(p) for p in sorted(project.raw.rglob("*")) if p.is_file()}
    assert before == after


def test_no_sources_still_renders_a_traceable_report(mutable_project):
    """Turning the pack off must degrade the download, not the lineage."""
    resolutions = mutable_project.config / "resolutions.demo.yaml"
    result = run(mutable_project, resolutions_path=resolutions, copy_sources=False)

    assert result.gate.passed is True
    assert not (result.outputs_dir / SOURCES_DIRNAME).exists()
    assert result.manifest["source_copies"] == {}

    files = result.summary.source_index["files"]
    assert files, "previews must still be embedded so a trace can be inspected"
    for document in files.values():
        assert document["download"] is None
        assert document["note"]


@pytest.mark.parametrize("copy_sources", [True, False])
def test_the_summary_is_self_contained_either_way(mutable_project, copy_sources):
    result = run(
        mutable_project,
        resolutions_path=mutable_project.config / "resolutions.demo.yaml",
        copy_sources=copy_sources,
    )
    html = (result.outputs_dir / "summary.html").read_text()

    assert 'id="pmp-source-index"' in html
    assert 'id="source-viewer"' in html
    assert "http://" not in html.replace("http://www.w3.org", "")  # no external fetches
