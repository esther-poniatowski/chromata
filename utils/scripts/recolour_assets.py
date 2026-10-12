"""
Repaint two-colour raster pictures into the two target tokens of a LaTeX palette.

Usage, from the workspace root (never from the base conda environment)::

    conda run -n geonexus python utils/scripts/recolour_assets.py \\
        --palette path/to/colors-values.tex --spec path/to/palette.toml \\
        --source path/to/assets --out path/to/new-assets

The ``[recolour]`` table of the specification names the two target tokens and the rows of pictures.
Pictures are written under their own filenames; the source folder is never modified, so a repaint
can be reviewed before it replaces anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

from palette_tools.colour import hex_to_srgb
from palette_tools.latex_palette import PaletteSourceError, read_palette
from palette_tools.recolour import RecolourError, recolour_row
from palette_tools.spec import SpecError, load_spec


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--palette", nargs="+", required=True, type=Path,
                        help="LaTeX palette sources, in load order")
    parser.add_argument("--spec", required=True, type=Path,
                        help="TOML specification holding a [recolour] table")
    parser.add_argument("--source", required=True, type=Path, help="folder of the source pictures")
    parser.add_argument("--out", required=True, type=Path, help="folder of the repainted pictures")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command; return the exit status."""
    args = build_parser().parse_args(argv)
    if args.out.resolve() == args.source.resolve():
        print("recolour_assets: --out must differ from --source", file=sys.stderr)
        return 2
    try:
        palette = read_palette(*args.palette)
        spec = load_spec(args.spec)
    except (PaletteSourceError, SpecError) as error:
        print(f"recolour_assets: {error}", file=sys.stderr)
        return 2
    plan = spec.recolour
    if plan is None:
        print("recolour_assets: the specification holds no [recolour] table", file=sys.stderr)
        return 2
    missing = [t for t in plan.targets if t not in palette]
    if missing:
        print(f"recolour_assets: target tokens absent from the palette: {missing}", file=sys.stderr)
        return 2
    targets = (np.array(hex_to_srgb(palette[plan.targets[0]])),
               np.array(hex_to_srgb(palette[plan.targets[1]])))
    print(f"=== targets: {plan.targets[0]} #{palette[plan.targets[0]]}, "
          f"{plan.targets[1]} #{palette[plan.targets[1]]} ===")
    try:
        for row in plan.rows:
            print()
            print("\n".join(recolour_row(row, args.source, args.out, targets)))
    except (RecolourError, FileNotFoundError) as error:
        print(f"recolour_assets: {error}", file=sys.stderr)
        return 2
    print(f"\nwrote {3 * len(plan.rows)} pictures to {args.out}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
