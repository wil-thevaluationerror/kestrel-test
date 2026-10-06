"""Same inputs and seed, same outputs. Without this, nothing else here is auditable."""

from pmp.configio import load_config
from pmp.generate import generate
from pmp.hashing import sha256_file
from pmp.pipeline import run

FIXED_TIME = "2026-10-06T12:00:00+00:00"


def test_generation_is_byte_stable(mutable_project):
    before = {
        path: sha256_file(path) for path in sorted(mutable_project.raw.rglob("*")) if path.is_file()
    }

    generate(load_config(mutable_project).fund, mutable_project)

    after = {
        path: sha256_file(path) for path in sorted(mutable_project.raw.rglob("*")) if path.is_file()
    }
    assert before == after


def test_two_runs_produce_the_same_run_id_and_input_hashes(project, demo_resolutions):
    first = run(project, resolutions_path=demo_resolutions, generated_at=FIXED_TIME)
    second = run(project, resolutions_path=demo_resolutions, generated_at=FIXED_TIME)

    assert first.run_id == second.run_id
    assert first.manifest["inputs"] == second.manifest["inputs"]
    assert first.manifest == second.manifest


def test_canonical_tables_are_identical_between_runs(project, demo_resolutions):
    first = run(project, resolutions_path=demo_resolutions, generated_at=FIXED_TIME)
    second = run(project, resolutions_path=demo_resolutions, generated_at=FIXED_TIME)

    assert first.canonical == second.canonical
    assert first.queue.exceptions == second.queue.exceptions


def test_output_files_are_byte_identical_between_runs(project, demo_resolutions):
    first = run(project, resolutions_path=demo_resolutions, generated_at=FIXED_TIME)
    captured = {path.name: path.read_bytes() for path in first.written}

    second = run(project, resolutions_path=demo_resolutions, generated_at=FIXED_TIME)

    assert {path.name for path in second.written} == set(captured)
    for path in second.written:
        assert path.read_bytes() == captured[path.name], f"{path.name} is not reproducible"
