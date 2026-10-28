"""Generate deterministic LaTeX and CSS projections from one palette specification."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chromata.cli_resources import add_resource_argument, resource_resolver
from chromata.emit import (
    ROLES_FILE,
    VALUES_FILE,
    ProjectionError,
    TeXProjection,
    css_block,
    display_path,
    outputs,
)
from chromata.spec import PaletteSpec, SpecError, load_spec


def _rename(value: str) -> tuple[str, str]:
    """Parse one ``SOURCE=TARGET`` TeX-name override."""
    source, separator, target = value.partition("=")
    if not separator or not source or not target:
        raise argparse.ArgumentTypeError("expected SOURCE=TARGET")
    return source, target


def _source_label(value: str) -> str:
    """Accept a source label that cannot terminate a generated comment."""
    if not value or "\n" in value or "\r" in value or "*/" in value:
        raise argparse.ArgumentTypeError("source label cannot contain a line break or `*/'")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec", required=True, type=Path, help="palette specification")
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help="local resource root against which path references resolve",
    )
    add_resource_argument(parser)
    parser.add_argument("--values-out", type=Path, help="target of the LaTeX value layer")
    parser.add_argument("--roles-out", type=Path, help="target of the LaTeX role layer")
    parser.add_argument("--css-out", type=Path, help="target of the standalone CSS block")
    parser.add_argument(
        "--source-label",
        type=_source_label,
        help="stable logical label printed in generated provenance comments",
    )
    parser.add_argument("--values-prefix", default="",
                        help="prefix of generated TeX value names")
    parser.add_argument("--roles-prefix", default="",
                        help="prefix of generated TeX role names")
    parser.add_argument(
        "--tex-name",
        action="append",
        default=[],
        type=_rename,
        metavar="SOURCE=TARGET",
        help="replace one palette name in the generated TeX interface; repeat as needed",
    )
    parser.add_argument("--check", action="store_true", help="report stale targets and write nothing")
    return parser


def _accept(target: Path, expected: str, *, check: bool) -> bool:
    """Check or write one target; return whether its prior contents were current."""
    current = target.read_text(encoding="utf-8") if target.exists() else None
    if current == expected:
        return True
    if check:
        print(f"stale: {target}")
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(expected, encoding="utf-8")
    print(f"wrote {target}")
    return True


def _source_paths(spec: PaletteSpec) -> set[Path]:
    """Return every palette file loaded into one specification."""
    paths: set[Path] = set()
    current: PaletteSpec | None = spec
    while current is not None:
        paths.add(current.path.resolve())
        current = current.base
    return paths


def _projection_problems(spec: PaletteSpec, args: argparse.Namespace) -> list[str]:
    """Return unsafe or ambiguous projection settings."""
    problems: list[str] = []
    if args.source_label is None:
        try:
            spec.path.relative_to(args.root.resolve())
        except ValueError:
            problems.append("a palette outside --root requires --source-label")
    if args.values_out is not None and not spec.layers:
        problems.append("--values-out was given for a palette without value layers")
    if args.roles_out is not None and not spec.roles:
        problems.append("--roles-out was given for a palette without roles")

    targets: list[Path] = []
    if spec.layers:
        targets.append((args.values_out or spec.path.parent / VALUES_FILE).resolve())
    if spec.roles:
        targets.append((args.roles_out or spec.path.parent / ROLES_FILE).resolve())
    if args.css_out is not None:
        targets.append(args.css_out.resolve())
    duplicates = {target for target in targets if targets.count(target) > 1}
    problems.extend(f"output target is declared twice: {target}" for target in sorted(duplicates))
    problems.extend(
        f"output target would overwrite a palette input: {target}"
        for target in sorted(set(targets) & _source_paths(spec))
    )

    entries: list[tuple[str, str]] = args.tex_name
    sources = [source for source, _ in entries]
    duplicate_sources = {source for source in sources if sources.count(source) > 1}
    problems.extend(f"TeX name is mapped twice: {source}" for source in sorted(duplicate_sources))
    return problems


def main(argv: list[str] | None = None) -> int:
    """Generate or check the requested projections."""
    args = build_parser().parse_args(argv)
    root = args.root.resolve()
    try:
        spec = load_spec(args.spec, root, resolver=resource_resolver(root, args.resource))
    except SpecError as error:
        print(f"chromata-build: {error}", file=sys.stderr)
        return 2

    problems = _projection_problems(spec, args)
    if problems:
        for problem in problems:
            print(f"chromata-build: {problem}", file=sys.stderr)
        return 2

    try:
        projection = TeXProjection.for_spec(
            spec,
            values_prefix=args.values_prefix,
            roles_prefix=args.roles_prefix,
            names=dict(args.tex_name),
        )
    except ProjectionError as error:
        print(f"chromata-build: {error}", file=sys.stderr)
        return 2

    rendered = outputs(
        spec,
        root,
        values_target=args.values_out,
        roles_target=args.roles_out,
        projection=projection,
        source_label=args.source_label,
    )
    if args.css_out is not None:
        if not spec.css:
            print("chromata-build: --css-out requires a palette with CSS bindings", file=sys.stderr)
            return 2
        source = args.source_label or display_path(spec.path, root)
        rendered[args.css_out] = css_block(spec, source, "") + "\n"

    if not rendered:
        print("chromata-build: the palette declares no projection", file=sys.stderr)
        return 2
    current = [_accept(target, text, check=args.check) for target, text in rendered.items()]
    return 0 if all(current) else 1


if __name__ == "__main__":
    sys.exit(main())
