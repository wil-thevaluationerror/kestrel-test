"""Deterministic text writing for csv source files and outputs."""

from __future__ import annotations

from pathlib import Path


def write_text(path: Path, text: str) -> None:
    """Write with explicit newlines so output bytes do not depend on the platform."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_rows(path: Path, header: list[str], rows: list[list[str]]) -> None:
    lines = [",".join(header)] + [",".join(row) for row in rows]
    write_text(path, "\n".join(lines) + "\n")


def fmt_number(value: float) -> str:
    """Render a number the way a reporting template would: whole dollars when whole,
    one decimal otherwise. Never scientific notation, which breaks naive parsers."""
    if abs(value - round(value)) < 1e-9:
        return f"{round(value):d}"
    return f"{value:.1f}"
