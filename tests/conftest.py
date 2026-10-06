"""Fixtures. Every test runs the pipeline against a temporary copy of the repo, never
against the checkout, so a test can never alter the data a reviewer is looking at."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from pmp.configio import load_config
from pmp.generate import generate
from pmp.paths import Layout, default_layout


def _scaffold(root: Path) -> Layout:
    source = default_layout()
    scratch = Layout(root=root)
    shutil.copytree(source.config, scratch.config)
    shutil.copytree(source.templates, scratch.templates)
    return scratch


@pytest.fixture(scope="session")
def project(tmp_path_factory) -> Layout:
    """Config, templates, and freshly generated synthetic data in a temp root."""
    scratch = _scaffold(tmp_path_factory.mktemp("pmp"))
    generate(load_config(scratch).fund, scratch)
    return scratch


@pytest.fixture
def mutable_project(tmp_path) -> Layout:
    """A per-test copy, for tests that need to change config or raw files."""
    scratch = _scaffold(tmp_path / "repo")
    generate(load_config(scratch).fund, scratch)
    return scratch


@pytest.fixture
def config(project):
    return load_config(project)


@pytest.fixture(scope="session")
def ground_truth(project) -> dict:
    return json.loads(project.ground_truth.read_text())


@pytest.fixture
def demo_resolutions(project) -> Path:
    return project.config / "resolutions.demo.yaml"
