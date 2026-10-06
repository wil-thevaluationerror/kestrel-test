"""`make demo-break`: a changed template label must stop the report, not corrupt it."""

from pmp.demo_break import prepare
from pmp.hashing import sha256_file
from pmp.pipeline import run


def test_renaming_a_label_raises_i01_and_withholds_the_report(mutable_project, tmp_path):
    scratch, changed = prepare(mutable_project, tmp_path / "break")

    result = run(scratch, resolutions_path=scratch.config / "resolutions.demo.yaml")

    open_unmapped = [
        e for e in result.queue.exceptions if e.rule_id == "I01" and e.status == "open"
    ]
    assert [e.holding_id for e in open_unmapped] == ["RE-C"]
    assert result.gate.passed is False
    assert not (result.outputs_dir / "summary.html").exists()
    assert changed.name.startswith("RE-C")


def test_the_original_raw_data_is_untouched(mutable_project, tmp_path):
    before = {
        path.name: sha256_file(path)
        for path in sorted(mutable_project.raw.rglob("*")) if path.is_file()
    }

    prepare(mutable_project, tmp_path / "break")

    after = {
        path.name: sha256_file(path)
        for path in sorted(mutable_project.raw.rglob("*")) if path.is_file()
    }
    assert before == after


def test_the_same_quarter_passes_the_gate_before_the_break(mutable_project):
    """The contrast is the point: signed off and reporting, until one label changes."""
    result = run(mutable_project, resolutions_path=mutable_project.config / "resolutions.demo.yaml")

    assert result.gate.passed is True
