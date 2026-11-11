"""Schemas installed with Chromata, and the validation shared by every record they govern."""

from __future__ import annotations

from collections.abc import Mapping
from importlib.resources import files
from typing import Any

import yaml
from jsonschema import Draft202012Validator

#: Schema of a palette specification.
PALETTE_SCHEMA = "palette.schema.yaml"

#: Schema of a build manifest.
MANIFEST_SCHEMA = "build-manifest.schema.yaml"

#: Key of a record naming its format.
FORMAT_KEY = "_schema"

#: Key that named the version of a format before ``_schema``, rejected with its replacement.
RETIRED_FORMAT_KEY = "schema_version"


def _format_problem(schema: Mapping[str, Any], data: Any) -> str | None:
    """
    Return the defect of the format declared by ``data``, or ``None`` when the format matches.

    The expected identifier is the value that the schema fixes under :data:`FORMAT_KEY`, and the
    message names it, so that the researcher reads the value to write.

    Parameters
    ----------
    schema : Mapping[str, Any]
        The loaded schema of the format.
    data : Any
        The record, as loaded from YAML. A record other than a mapping is left to the schema.

    Returns
    -------
    str or None
        The ``location: message`` entry of the defect, or ``None``.
    """
    if not isinstance(data, Mapping):
        return None
    expected = schema["properties"][FORMAT_KEY]["const"]
    instruction = f"write {FORMAT_KEY}: {expected} as the first key"
    if RETIRED_FORMAT_KEY in data:
        return f"{RETIRED_FORMAT_KEY}: retired; {instruction}"
    if FORMAT_KEY not in data:
        return f"{FORMAT_KEY}: absent; {instruction}"
    if data[FORMAT_KEY] != expected:
        return f"{FORMAT_KEY}: {data[FORMAT_KEY]}, expected {expected}"
    return None


def schema_violations(name: str, data: Any) -> list[str]:
    """
    Return each violation of an installed schema by ``data``, located by its path in the record.

    A record declaring another format than the schema reports this defect alone, since its other
    keys belong to a format that the schema does not describe.

    Parameters
    ----------
    name : str
        The file name of an installed schema, such as :data:`PALETTE_SCHEMA`.
    data : Any
        The record, as loaded from YAML.

    Returns
    -------
    list[str]
        One ``location: message`` entry per violation, sorted by location.
    """
    with files(__name__).joinpath(name).open(encoding="utf-8") as handle:
        schema = yaml.safe_load(handle)
    problem = _format_problem(schema, data)
    if problem is not None:
        return [problem]
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in errors]
