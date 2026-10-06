"""Command line entry points. One command per stage so a reviewer can stop and look."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .configio import load_config
from .demo_break import prepare
from .generate import generate
from .paths import Layout, default_layout
from .pipeline import run


def _layout(args: argparse.Namespace) -> Layout:
    return Layout(root=Path(args.root).resolve()) if args.root else default_layout()


def cmd_data(args: argparse.Namespace) -> int:
    layout = _layout(args)
    config = load_config(layout)
    files = generate(config.fund, layout)
    print(f"generated {len(files)} source files under {layout.raw}")
    print(f"defect manifest: {layout.ground_truth}")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    layout = _layout(args)
    resolutions = Path(args.resolutions).resolve() if args.resolutions else None
    result = run(
        layout, resolutions_path=resolutions, period_label=args.period,
        copy_sources=not args.no_sources,
    )

    print(f"run {result.run_id}")
    print(f"exceptions: {len(result.queue.exceptions)} "
          f"({result.manifest['exception_counts']['open']} open)")
    print(result.gate.message())
    for path in result.written:
        print(f"  wrote {path.relative_to(layout.root)}")
    if not result.gate.passed:
        print("\nNo fund summary was generated. The gate is doing its job.")
        return 1
    return 0


def cmd_demo_break(args: argparse.Namespace) -> int:
    """Show the pipeline refusing to report on an unmappable file. Exit 0 when it refuses."""
    layout = _layout(args)
    scratch, path = prepare(layout, layout.root / ".demo-break")
    print(f"renamed one label in a copy: {path.name}\n")
    # Run against the signed-off resolutions, so the only unresolved problem is the rename.
    result = run(scratch, resolutions_path=scratch.config / "resolutions.demo.yaml")
    unmapped = [
        e for e in result.queue.exceptions if e.rule_id == "I01" and e.status == "open"
    ]
    print(result.gate.message())
    print()
    if result.gate.passed or not unmapped:
        print("DEMO-BREAK FAILED: the pipeline reported on data it could not map.")
        return 1
    print(f"DEMO-BREAK PASS: {len(unmapped)} unmapped label exception(s) raised and no "
          "summary was produced. data/raw/ was not modified.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pmp", description="Portfolio monitoring pipeline")
    parser.add_argument("--root", help="repo root to operate on (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)

    data = sub.add_parser("data", help="generate synthetic source reports and ground truth")
    data.set_defaults(func=cmd_data)

    pipeline = sub.add_parser("run", help="ingest, check, gate, and report")
    pipeline.add_argument("--resolutions", help="path to a resolutions file")
    pipeline.add_argument("--period", help="reporting period label, e.g. 2026Q2")
    pipeline.add_argument(
        "--no-sources",
        action="store_true",
        help="do not copy the ingested source documents next to the report",
    )
    pipeline.set_defaults(func=cmd_run)

    broken = sub.add_parser("demo-break", help="rename a label in a copy of raw data and run")
    broken.set_defaults(func=cmd_demo_break)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
