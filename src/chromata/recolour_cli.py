"""
Repaint two-colour raster pictures into the two target tokens of a palette.

Usage::

    chromata-recolour --spec path/to/palette.yml [--palette path/to/scheme.tex ...] \\
        --source path/to/assets --output-dir path/to/new-assets

The ``recolour`` table of the palette names the two target tokens and the rows of pictures.
Pictures are written under their own filenames inside the output folder, which they never leave;
no source picture is ever overwritten, so a repaint can be reviewed before it replaces anything.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from chromata.check_cli import measured_palette
from chromata.cli_resources import add_resource_argument, resource_resolver
from chromata.cli_settings import add_root_argument, resolve_root
from chromata.colour import hex_to_srgb
from chromata.latex_palette import PaletteSourceError
from chromata.spec import RecolourRow, SpecError, load_spec


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface."""
    parser = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[0],
        allow_abbrev=False,   # a prefix would revive a retired name, such as --out
    )
    parser.add_argument("--spec", required=True, type=Path,
                        help="the palette file, palette.yml, holding a recolour table")
    parser.add_argument("--palette", nargs="+", default=[], type=Path,
                        help="LaTeX sources overriding token values, such as a candidate scheme")
    parser.add_argument("--source", required=True, type=Path, help="folder of the source pictures")
    parser.add_argument("--output-dir", required=True, type=Path,
                        help="folder of the repainted pictures")
    add_root_argument(parser)
    add_resource_argument(parser)
    return parser


def _pictures(row: RecolourRow) -> tuple[str, str, str]:
    """Return the three picture names of a row."""
    return row.first, row.second, row.mixture


def unsafe_outputs(rows: Sequence[RecolourRow], source: Path, output_dir: Path) -> list[str]:
    """
    Return one problem per repainted picture that would land outside its folder or on a source.

    A picture name may hold a folder part, so the check compares resolved paths rather than the
    two folders alone: a repaint never writes outside ``output_dir``, and never overwrites a
    source picture of any row, which Chromata cannot regenerate.

    Examples
    --------
    >>> nested = RecolourRow("row", "unmix", "a.png", "new/a.png", "ab.png")
    >>> unsafe_outputs([nested], Path("/assets"), Path("/assets/new"))
    ['a.png: the repainted picture would overwrite the source /assets/new/a.png']
    >>> escaping = RecolourRow("row", "unmix", "a.png", "b.png", "../ab.png")
    >>> unsafe_outputs([escaping], Path("/b/source"), Path("/a/output"))
    ['../ab.png: the repainted picture would leave the output folder /a/output']
    """
    folder = output_dir.resolve()
    sources = {(source / name).resolve() for row in rows for name in _pictures(row)}
    problems = []
    for row in rows:
        for name in _pictures(row):
            target = (output_dir / name).resolve()
            if target in sources:
                problems.append(f"{name}: the repainted picture would overwrite the source {target}")
            elif folder not in target.parents:
                problems.append(f"{name}: the repainted picture would leave the output folder {folder}")
    return problems


def main(argv: list[str] | None = None) -> int:
    """Run the command; return the exit status."""
    args = build_parser().parse_args(argv)
    try:
        import numpy as np

        from chromata.recolour import RecolourError, recolour_row
    except ModuleNotFoundError:
        print(
            "chromata-recolour: raster support is not installed; install `chromata[raster]'",
            file=sys.stderr,
        )
        return 2
    if args.output_dir.resolve() == args.source.resolve():
        print("chromata-recolour: --output-dir must differ from --source", file=sys.stderr)
        return 2
    root = resolve_root(args.root)
    try:
        resolver = resource_resolver(root, args.resource)
        palette = measured_palette(args.spec, args.palette, None, root, resolver)
        spec = load_spec(args.spec, root, resolver=resolver)
    except (PaletteSourceError, SpecError) as error:
        print(f"chromata-recolour: {error}", file=sys.stderr)
        return 2
    plan = spec.recolour
    if plan is None:
        print("chromata-recolour: the palette holds no recolour table", file=sys.stderr)
        return 2
    unsafe = unsafe_outputs(plan.rows, args.source, args.output_dir)
    if unsafe:
        for problem in unsafe:
            print(f"chromata-recolour: {problem}", file=sys.stderr)
        return 2
    missing = [t for t in plan.targets if t not in palette]
    if missing:
        print(f"chromata-recolour: target tokens absent from the palette: {missing}", file=sys.stderr)
        return 2
    targets = (np.array(hex_to_srgb(palette[plan.targets[0]])),
               np.array(hex_to_srgb(palette[plan.targets[1]])))
    print(f"=== targets: {plan.targets[0]} #{palette[plan.targets[0]]}, "
          f"{plan.targets[1]} #{palette[plan.targets[1]]} ===")
    try:
        for row in plan.rows:
            print()
            print("\n".join(recolour_row(row, args.source, args.output_dir, targets)))
    except (RecolourError, FileNotFoundError) as error:
        print(f"chromata-recolour: {error}", file=sys.stderr)
        return 2
    print(f"\nwrote {3 * len(plan.rows)} pictures to {args.output_dir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
