"""Filesystem layout. Every path the pipeline touches is resolved through here so tests
can run the whole pipeline against a temporary tree without monkeypatching modules."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Layout:
    root: Path

    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def mappings(self) -> Path:
        return self.config / "mappings"

    @property
    def raw(self) -> Path:
        return self.root / "data" / "raw"

    @property
    def staged(self) -> Path:
        return self.root / "data" / "staged"

    @property
    def warehouse(self) -> Path:
        return self.root / "data" / "warehouse.duckdb"

    @property
    def ground_truth(self) -> Path:
        return self.root / "data" / "ground_truth.json"

    @property
    def templates(self) -> Path:
        return self.root / "templates"

    def outputs(self, run_id: str) -> Path:
        return self.root / "outputs" / run_id


def default_layout() -> Layout:
    return Layout(root=REPO_ROOT)


def display_path(path: Path, root: Path) -> str:
    """Repo-relative where possible, absolute otherwise.

    A reviewer may legitimately point --resolutions at a file outside the checkout. That has
    to be recorded honestly rather than crash the run.
    """
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)
