"""
Measure a LaTeX colour palette against a consumer's acceptance tests.

Usage, from the workspace root (never from the base conda environment)::

    conda run -n geonexus python utils/scripts/check_palette.py \\
        --palette path/to/colors-values.tex [path/to/scheme.tex ...] --spec path/to/palette.toml
    ... --grey-for chromecore           # the neutral grey matching a token's lightness
    ... --emit-proof proof.tex          # a self-contained proof sheet, then exit

The palette files are read in order, so a later file overrides an earlier one; that order is how a
candidate scheme is measured on top of base values. The exit status is 1 when a binding test fails,
so the command can gate a build.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from palette_tools.colour import contrast, grey_matching, oklab
from palette_tools.latex_palette import PaletteSourceError, read_palette
from palette_tools.proof import proof_sheet
from palette_tools.report import report
from palette_tools.spec import SpecError, load_spec


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--palette", nargs="+", required=True, type=Path,
                        help="LaTeX palette sources, in load order")
    parser.add_argument("--spec", type=Path, help="TOML specification of the acceptance tests")
    parser.add_argument("--label", help="name printed in the report (default: the last palette file)")
    parser.add_argument("--grey-for", metavar="TOKEN",
                        help="print the neutral grey matching that token's OKLab lightness, and exit")
    parser.add_argument("--emit-proof", metavar="PATH", type=Path,
                        help="write a self-contained LaTeX proof sheet, and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command; return the exit status."""
    args = build_parser().parse_args(argv)
    try:
        palette = read_palette(*args.palette)
        spec = load_spec(args.spec) if args.spec else None
    except (PaletteSourceError, SpecError) as error:
        print(f"check_palette: {error}", file=sys.stderr)
        return 2
    label = args.label or args.palette[-1].name
    tests = spec.tests if spec else None

    if args.grey_for:
        token = args.grey_for
        if token not in palette:
            print(f"check_palette: unknown token: {token}", file=sys.stderr)
            return 2
        grey = grey_matching(palette[token])
        ground = palette.get(tests.ground, "FFFFFF") if tests else "FFFFFF"
        print(f"{token} = {palette[token]} (OKLab L {oklab(palette[token])[0]:.3f}) "
              f"-> matching grey {grey} (L {oklab(grey)[0]:.3f}, "
              f"contrast on ground {contrast(grey, ground):.2f}:1)")
        return 0

    if args.emit_proof:
        args.emit_proof.parent.mkdir(parents=True, exist_ok=True)
        args.emit_proof.write_text(proof_sheet(palette, label, tests), encoding="utf-8")
        print(f"wrote {args.emit_proof} ({len(palette)} tokens)")
        return 0

    if tests is None:
        print("check_palette: --spec with a [tests] table is required for the report", file=sys.stderr)
        return 2
    text, failures = report(palette, tests, label)
    print(text)
    print(f"\n{failures} binding failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
