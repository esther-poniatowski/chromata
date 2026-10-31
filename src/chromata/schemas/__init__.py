"""Schemas installed with Chromata, and the validation shared by every record they govern."""

from __future__ import annotations

from importlib.resources import files
from typing import Any

import yaml
from jsonschema import Draft202012Validator

#: Schema of a palette specification.
PALETTE_SCHEMA = "palette.schema.yaml"

#: Schema of a build manifest.
MANIFEST_SCHEMA = "build-manifest.schema.yaml"


def schema_violations(name: str, data: Any) -> list[str]:
    """
    Return each violation of an installed schema by ``data``, located by its path in the record.

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
        validator = Draft202012Validator(yaml.safe_load(handle))
    errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
    return [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in errors]
