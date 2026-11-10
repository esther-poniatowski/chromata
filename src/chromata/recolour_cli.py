"""
Repaint two-colour raster pictures into the two target tokens of a palette.

Usage::

    chromata-recolour --root . \\
        --spec path/to/palette.yml [--palette path/to/scheme.tex ...] \\
        --source path/to/assets --output-dir path/to/new-assets

The ``recolour`` table of the palette names the two target tokens and the rows of pictures.
Pictures are written under their own filenames; the source folder is never modified, so a repaint
can be reviewed before it replaces anything.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chromata.check_cli import measured_palette
from chromata.cli_resources import add_resource_argument, resource_resolver
from chromata.colour import hex_to_srgb
from chromata.latex_palette import PaletteSourceError
from chromata.spec import SpecError, load_spec


class _DeprecatedOutAlias(argparse.Action):
    """Accept the former ``--out`` name of ``--output-dir`` for one release, with a warning."""

    def __call__(self, parser, namespace, values, option_string=None):
        print("chromata-recolour: warning: --out is deprecated; use --output-dir", file=sys.stderr)
        setattr(namespace, self.dest, values)


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--spec", required=True, type=Path,
                        help="the palette file, palette.yml, holding a recolour table")
    parser.add_argument("--palette", nargs="+", default=[], type=Path,
                        help="LaTeX sources overriding token values, such as a candidate scheme")
    parser.add_argument("--source", required=True, type=Path, help="folder of the source pictures")
    output = parser.add_mutually_exclusive_group(required=True)
    output.add_argument("--output-dir", type=Path, help="folder of the repainted pictures")
    output.add_argument("--out", dest="output_dir", type=Path, action=_DeprecatedOutAlias,
                        help=argparse.SUPPRESS)
    parser.add_argument("--root", required=True, type=Path,
                        help="local resource root against which path references resolve")
    add_resource_argument(parser)
    return parser


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
    try:
        resolver = resource_resolver(args.root, args.resource)
        palette = measured_palette(args.spec, args.palette, None, args.root, resolver)
        spec = load_spec(args.spec, args.root, resolver=resolver)
    except (PaletteSourceError, SpecError) as error:
        print(f"chromata-recolour: {error}", file=sys.stderr)
        return 2
    plan = spec.recolour
    if plan is None:
        print("chromata-recolour: the palette holds no recolour table", file=sys.stderr)
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
