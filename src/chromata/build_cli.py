"""
Generate deterministic LaTeX and CSS projections from palette specifications.

``--spec`` projects one palette, configured by the options of this command. Without ``--spec``,
the command projects every palette listed in its configuration file, ``chromata.yml``, a build
manifest read from ``--config``, else from ``config/tools/chromata.yml`` or ``chromata.yml``
below the root, in one run with one exit status. ``--css-page``, or the ``css_pages`` key of a manifest entry,
refreshes the block marked with the palette's source label inside an existing web page, and leaves
every byte outside that block unchanged.

Every input is checked before any target is written. The exit status is 0 when every target is
current or written, 1 when ``--check`` finds a stale target, and 2 when an input is invalid.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from chromata.build import (
    BuildRequest,
    changed_targets,
    comment_label_problem,
    plan_build,
    shown,
    write_targets,
)
from chromata.cli_resources import add_resource_argument, resource_resolver
from chromata.cli_settings import (
    SETTINGS_LOCATIONS,
    add_root_argument,
    locate_settings,
    resolve_root,
)
from chromata.manifest import ManifestError, load_manifest
from chromata.spec import SpecError

#: Options that configure one palette, which a manifest entry declares instead.
PER_PALETTE_OPTIONS: dict[str, str] = {
    "values_output": "--values-output",
    "roles_output": "--roles-output",
    "css_output": "--css-output",
    "css_page": "--css-page",
    "source_label": "--source-label",
    "values_prefix": "--values-prefix",
    "roles_prefix": "--roles-prefix",
    "tex_name": "--tex-name",
}


def _rename(value: str) -> tuple[str, str]:
    """Parse one ``SOURCE=TARGET`` TeX-name override."""
    source, separator, target = value.partition("=")
    if not separator or not source or not target:
        raise argparse.ArgumentTypeError("expected SOURCE=TARGET")
    return source, target


def _source_label(value: str) -> str:
    """Accept a source label that cannot terminate a generated comment."""
    problem = comment_label_problem(value)
    if problem is not None:
        raise argparse.ArgumentTypeError(problem)
    return value


def build_parser() -> argparse.ArgumentParser:
    """Return the command-line parser."""
    parser = argparse.ArgumentParser(
        description=__doc__.strip().splitlines()[0],
        allow_abbrev=False,   # a prefix would revive a retired name, such as --out
    )
    inputs = parser.add_mutually_exclusive_group()
    inputs.add_argument("--spec", type=Path, help="palette specification")
    inputs.add_argument(
        "-c",
        "--config",
        type=Path,
        help="configuration file, a build manifest listing every palette of the run and its "
             "targets (default: config/tools/chromata.yml or chromata.yml below the root)",
    )
    add_root_argument(parser)
    add_resource_argument(parser)
    parser.add_argument("--values-output", type=Path, help="target of the LaTeX value layer")
    parser.add_argument("--roles-output", type=Path, help="target of the LaTeX role layer")
    parser.add_argument("--css-output", type=Path, help="target of the standalone CSS block")
    parser.add_argument(
        "--css-page",
        action="append",
        default=[],
        type=Path,
        metavar="PAGE",
        help="web page whose block marked with the source label is refreshed in place; "
             "repeat as needed",
    )
    parser.add_argument(
        "--source-label",
        type=_source_label,
        help="stable logical label printed in generated provenance comments",
    )
    parser.add_argument("--values-prefix", help="prefix of generated TeX value names")
    parser.add_argument("--roles-prefix", help="prefix of generated TeX role names")
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


def _settings_file(args: argparse.Namespace, root: Path) -> Path:
    """
    Return the configuration file of a run without ``--spec``.

    Raises
    ------
    ManifestError
        If the root holds two configuration files, or none while ``--config`` is absent.
    """
    if args.config is not None:
        return args.config
    found = locate_settings(root)
    if found is None:
        places = " or ".join(str(root / location) for location in SETTINGS_LOCATIONS)
        raise ManifestError(f"nothing to build: pass --spec or --config, or write {places}")
    return found


def _requests(args: argparse.Namespace, root: Path) -> tuple[BuildRequest, ...]:
    """
    Return the build requests of the run.

    Raises
    ------
    ManifestError
        If the configuration file is absent or invalid, or a per-palette option accompanies it.
    """
    if args.spec is not None:
        return (BuildRequest(
            spec=args.spec,
            values_out=args.values_output,
            roles_out=args.roles_output,
            css_out=args.css_output,
            css_pages=tuple(args.css_page),
            source_label=args.source_label,
            values_prefix=args.values_prefix or "",
            roles_prefix=args.roles_prefix or "",
            tex_names=tuple(args.tex_name),
        ),)
    given = [option for key, option in PER_PALETTE_OPTIONS.items() if getattr(args, key)]
    if given:
        raise ManifestError(f"{', '.join(given)}: declare per-palette settings in the manifest")
    return load_manifest(_settings_file(args, root), root)


def main(argv: list[str] | None = None) -> int:
    """Generate or check the requested projections."""
    args = build_parser().parse_args(argv)
    root = resolve_root(args.root)
    try:
        resolver = resource_resolver(root, args.resource)
        requests = _requests(args, root)
    except (ManifestError, SpecError) as error:
        print(f"chromata-build: {error}", file=sys.stderr)
        return 2

    plan = plan_build(requests, root, resolver, exhaustive_pages=args.spec is None)
    if plan.problems:
        for problem in plan.problems:
            print(f"chromata-build: {problem}", file=sys.stderr)
        return 2

    changed = changed_targets(plan)
    if args.check:
        for target in changed:
            print(f"stale: {shown(target, root)}")
    else:
        write_targets(plan, changed)
        for target in changed:
            print(f"wrote {shown(target, root)}")
    outcome = "stale" if args.check else "written"
    print(f"{plan.palettes} palette(s), {len(plan.texts)} target(s): {len(changed)} {outcome}")
    return 1 if args.check and changed else 0


if __name__ == "__main__":
    sys.exit(main())
