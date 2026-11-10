"""
A build manifest: every palette of a consumer and the targets of its projections, declared once.

The consumer lists its palettes in one YAML file under the installed manifest schema: the settings
file of Chromata, ``chromata.yml``. Each entry holds the settings that ``chromata-build`` accepts
for one palette. Every path is relative to the resource root and must stay inside it, so a manifest
means the same on every machine and in either place of the settings file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from chromata.build import BuildRequest
from chromata.schemas import MANIFEST_SCHEMA, schema_violations


class ManifestError(ValueError):
    """Raised when a build manifest is missing, malformed, or names a path outside the root."""


def _confined(root: Path, value: str, where: str) -> Path:
    """Resolve a manifest path below ``root``, rejecting an escape."""
    target = (root / value).resolve()
    if root not in target.parents:
        raise ManifestError(f"{where}: path escapes the resource root: {value}")
    return target


def _request(root: Path, entry: dict[str, Any], index: int) -> BuildRequest:
    """Convert one manifest entry into a build request."""
    where = f"palettes/{index}"

    def optional(key: str) -> Path | None:
        return _confined(root, entry[key], f"{where}/{key}") if key in entry else None

    return BuildRequest(
        spec=_confined(root, entry["spec"], f"{where}/spec"),
        values_out=optional("values_output"),
        roles_out=optional("roles_output"),
        css_out=optional("css_output"),
        css_pages=tuple(
            _confined(root, page, f"{where}/css_pages") for page in entry.get("css_pages", [])
        ),
        source_label=entry.get("source_label"),
        values_prefix=entry.get("values_prefix", ""),
        roles_prefix=entry.get("roles_prefix", ""),
        tex_names=tuple(entry.get("tex_names", {}).items()),
    )


def load_manifest(path: Path, root: Path) -> tuple[BuildRequest, ...]:
    """
    Load a build manifest and return one build request per listed palette.

    Parameters
    ----------
    path : Path
        The manifest file.
    root : Path
        The resource root, against which every path of the manifest resolves.

    Returns
    -------
    tuple[BuildRequest, ...]
        The requests, in manifest order.

    Raises
    ------
    ManifestError
        If the file is missing, breaks the schema, or names a path outside ``root``.
    """
    if not path.is_file():
        raise ManifestError(f"no such settings file: {path}")
    try:
        with path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        raise ManifestError(f"{path}: malformed YAML: {error}") from error
    violations = schema_violations(MANIFEST_SCHEMA, data)
    if violations:
        raise ManifestError(f"{path}: schema violation: {'; '.join(violations)}")
    resolved = root.resolve()
    return tuple(_request(resolved, entry, index) for index, entry in enumerate(data["palettes"]))
