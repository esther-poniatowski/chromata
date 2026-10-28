"""Shared command-line bindings from logical palette references to local files."""

from __future__ import annotations

import argparse
from pathlib import Path

from chromata.spec import LocalResolver, MappedResolver, ResourceResolver, SpecError


def resource_binding(value: str) -> tuple[str, Path]:
    """Parse one ``REFERENCE=PATH`` resource binding."""
    reference, separator, path = value.partition("=")
    if not separator or not reference or not path:
        raise argparse.ArgumentTypeError("expected REFERENCE=PATH")
    return reference, Path(path)


def add_resource_argument(parser: argparse.ArgumentParser) -> None:
    """Add the repeatable logical-resource option shared by every command."""
    parser.add_argument(
        "--resource",
        action="append",
        default=[],
        type=resource_binding,
        metavar="REFERENCE=PATH",
        help="bind one logical palette reference to a resolved local file; repeat as needed",
    )


def resource_resolver(
    root: Path,
    bindings: list[tuple[str, Path]],
) -> ResourceResolver:
    """Construct the local resolver extended by unique exact bindings."""
    references = [reference for reference, _ in bindings]
    duplicates = sorted({reference for reference in references if references.count(reference) > 1})
    if duplicates:
        raise SpecError("logical resource is bound twice: " + ", ".join(duplicates))
    local = LocalResolver(root)
    return MappedResolver(local, dict(bindings)) if bindings else local
