"""
Generate the LaTeX layers and the CSS blocks of every palette, and check that no colour escapes one.

Usage, from the workspace root (never from the base conda environment)::

    conda run -n geonexus python utils/scripts/build_palette.py           # write every output
    conda run -n geonexus python utils/scripts/build_palette.py --check   # report stale outputs

The command finds every ``palette.yml`` under ``artifacts/``, loads it under the palette schema,
and writes its LaTeX layers beside it. A web page receives the CSS block of a palette between an
opening marker ``/* palette: <path of the palette> */`` and a closing marker ``/* palette: end */``.

A colour value is defined in a palette and nowhere else. The command therefore reports every
``\\definecolor`` of a LaTeX source under ``artifacts/``, apart from three kinds of file:

- a layer generated from a palette;
- a class file (``.cls``), or a file under ``_templates/``, which a venue supplies unchanged;
- a file under ``archive/``, which no build reads.

The exit status is 1 when an output is stale under ``--check``, or when a palette fails to load
or a source defines a colour.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from palette_tools.emit import css_block, outputs
from palette_tools.spec import PaletteSpec, SpecError, load_spec
from vault_paths import DEFAULT_ROOT

OPEN_RE = re.compile(r"^(?P<indent>[ \t]*)/\* palette: (?P<source>\S+palette\.yml)\b.*\*/[ \t]*$")
CLOSE_RE = re.compile(r"^[ \t]*/\* palette: end \*/[ \t]*$")
DEFINE_RE = re.compile(r"^[^%]*\\definecolor\b")


def _files(root: Path, *patterns: str) -> list[Path]:
    """Tracked and untracked files under ``artifacts/`` matching the patterns, ignored files excluded."""
    listed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", *patterns],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.splitlines()
    return sorted({root / line for line in listed if (root / line).exists()})


def _html_update(text: str, palettes: dict[str, PaletteSpec]) -> tuple[str, list[str]]:
    """Replace every marked block of a page; return the new text and the problems found."""
    lines, out, problems, i = text.split("\n"), [], [], 0
    while i < len(lines):
        match = OPEN_RE.match(lines[i])
        if match is None:
            out.append(lines[i])
            i += 1
            continue
        end = next((j for j in range(i + 1, len(lines)) if CLOSE_RE.match(lines[j])), None)
        spec = palettes.get(match["source"])
        if end is None or spec is None or not spec.css:
            problems.append(f"line {i + 1}: block of `{match['source']}' has no closing marker, "
                            "no loaded palette, or no CSS names")
            out.append(lines[i])
            i += 1
            continue
        out.append(css_block(spec, match["source"], match["indent"]))
        i = end + 1
    return "\n".join(out), problems


def main(argv: list[str] | None = None) -> int:
    """Run the command; return the exit status."""
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report stale outputs, write nothing")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="vault root")
    args = parser.parse_args(argv)
    root = args.root.resolve()

    failures = 0
    palettes: dict[str, PaletteSpec] = {}
    generated: set[Path] = set()
    for path in _files(root, "artifacts/*palette.yml"):
        if path.name != "palette.yml":
            continue
        try:
            spec = load_spec(path, root)
        except SpecError as error:
            print(f"error: {error}")
            failures += 1
            continue
        palettes[path.relative_to(root).as_posix()] = spec
        for target, text in outputs(spec, root).items():
            generated.add(target)
            current = target.read_text(encoding="utf-8") if target.exists() else None
            if current == text:
                continue
            rel = target.relative_to(root).as_posix()
            if args.check:
                print(f"stale: {rel}")
                failures += 1
            else:
                target.write_text(text, encoding="utf-8")
                print(f"wrote {rel}")

    for page in _files(root, "artifacts/*.html"):
        text = page.read_text(encoding="utf-8")
        if "/* palette:" not in text:
            continue
        new, problems = _html_update(text, palettes)
        rel = page.relative_to(root).as_posix()
        for problem in problems:
            print(f"error: {rel}: {problem}")
        failures += len(problems)
        if new == text:
            continue
        if args.check:
            print(f"stale: {rel}")
            failures += 1
        else:
            page.write_text(new, encoding="utf-8")
            print(f"wrote {rel}")

    for source in _files(root, "artifacts/*.tex", "artifacts/*.sty"):
        parts = source.relative_to(root).parts
        if source in generated or "_templates" in parts or "archive" in parts:
            continue
        for number, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1):
            if DEFINE_RE.match(line):
                print(f"error: {source.relative_to(root).as_posix()}:{number}: "
                      "a colour is defined outside a palette")
                failures += 1

    print(f"{len(palettes)} palette(s), {len(generated)} LaTeX layer(s): {failures} problem(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
