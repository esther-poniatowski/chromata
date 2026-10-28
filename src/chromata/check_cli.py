"""
Measure a colour palette against its acceptance tests.

Usage::

    chromata-check --root . \\
        --spec path/to/palette.yml [--palette path/to/scheme.tex ...] [--mode dark]
    ... --grey-for chromecore           # the neutral grey matching a token's lightness
    ... --emit-proof proof.tex          # a self-contained proof sheet, then exit

The values come from the palette file, then from the LaTeX sources given to ``--palette``, read in
order, so that a later file overrides an earlier one; that order is how a candidate scheme is
measured on top of the palette. The roles of the palette are bound last. The exit status is 1 when
a binding test fails, so the command can gate a build; a mark that the palette accepts under the
contrast floor does not fail it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chromata.cli_resources import add_resource_argument, resource_resolver
from chromata.colour import contrast, grey_matching, oklab
from chromata.latex_palette import PaletteSourceError, parse_palette
from chromata.proof import proof_sheet
from chromata.report import report
from chromata.spec import ResourceResolver, SpecError, load_spec


def build_parser() -> argparse.ArgumentParser:
    """The command-line interface."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--spec", required=True, type=Path, help="the palette file, palette.yml")
    parser.add_argument("--palette", nargs="+", default=[], type=Path,
                        help="LaTeX sources overriding token values, such as a candidate scheme, in load order")
    parser.add_argument("--mode", help="measure the palette in one of its modes, such as dark, "
                                       "against the tests of that mode")
    parser.add_argument("--label", help="name printed in the report (default: the last palette file)")
    parser.add_argument("--root", required=True, type=Path,
                        help="local resource root against which path references resolve")
    add_resource_argument(parser)
    parser.add_argument("--grey-for", metavar="TOKEN",
                        help="print the neutral grey matching that token's OKLab lightness, and exit")
    parser.add_argument("--emit-proof", metavar="PATH", type=Path,
                        help="write a self-contained LaTeX proof sheet, and exit")
    return parser


def measured_palette(
    spec_path: Path,
    overrides: list[Path],
    mode: str | None,
    root: Path,
    resolver: ResourceResolver | None = None,
) -> dict[str, str]:
    """
    ``name -> RRGGBB`` of a palette, with the overrides of a candidate scheme, and its roles bound.

    Raises
    ------
    SpecError
        If the palette fails to load, or the mode is not declared.
    PaletteSourceError
        If an override source does not exist.
    """
    spec = load_spec(spec_path, root, resolver=resolver)
    if mode is not None and not spec.has_mode(mode):
        raise SpecError(f"{spec_path}: no mode `{mode}'")
    values = spec.token_values(mode)
    for path in overrides:
        if not path.exists():
            raise PaletteSourceError(f"no such palette source: {path}")
        values = parse_palette(path.read_text(encoding="utf-8"), values)
    return spec.override_roles(spec.bind_roles(values), mode)


def main(argv: list[str] | None = None) -> int:
    """Run the command; return the exit status."""
    args = build_parser().parse_args(argv)
    try:
        resolver = resource_resolver(args.root, args.resource)
        palette = measured_palette(args.spec, args.palette, args.mode, args.root, resolver)
        spec = load_spec(args.spec, args.root, resolver=resolver)
    except (PaletteSourceError, SpecError) as error:
        print(f"chromata-check: {error}", file=sys.stderr)
        return 2
    label = args.label or (args.palette[-1].name if args.palette else args.spec.parent.name)
    if args.mode:
        label += f" ({args.mode})"
    tests = spec.tests_for(args.mode)

    if args.grey_for:
        token = args.grey_for
        if token not in palette:
            print(f"chromata-check: unknown token: {token}", file=sys.stderr)
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
        where = f"mode `{args.mode}'" if args.mode else "palette"
        print(f"chromata-check: the {where} declares no tests", file=sys.stderr)
        return 2
    text, failures = report(palette, tests, label)
    print(text)
    print(f"\n{failures} binding failure(s), {len(tests.accepted)} accepted.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
