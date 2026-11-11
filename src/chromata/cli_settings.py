"""
Shared command-line resolution of the resource root and of the configuration file.

Every command resolves its root in one order, and stops at the first answer: the option ``--root``,
the environment variable ``CHROMATA_ROOT``, the nearest ancestor of the current folder that holds
``chromata.yml`` in its ``config/tools/`` or at its own level, and the current folder. The settings
file, ``chromata.yml``, is the build manifest that ``chromata-build`` reads; its paths are relative
to the root.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from chromata.manifest import ManifestError

#: Environment variable naming the resource root.
ROOT_ENV = "CHROMATA_ROOT"

#: Name of the configuration file of Chromata.
SETTINGS_FILENAME = "chromata.yml"

#: Places of the configuration file below a root; a root holding both is an error.
SETTINGS_LOCATIONS = (Path("config") / "tools" / SETTINGS_FILENAME, Path(SETTINGS_FILENAME))


def add_root_argument(parser: argparse.ArgumentParser) -> None:
    """Add the optional ``-r``, ``--root`` option shared by every command."""
    parser.add_argument(
        "-r",
        "--root",
        type=Path,
        help="resource root against which palette references and the paths of chromata.yml "
             f"resolve (default: {ROOT_ENV}, else the nearest ancestor holding chromata.yml, "
             "else the current folder)",
    )


def _holds_settings(directory: Path) -> bool:
    """Return whether ``directory`` holds a configuration file at one of its places."""
    return any((directory / location).is_file() for location in SETTINGS_LOCATIONS)


def resolve_root(option: Path | None) -> Path:
    """
    Return the absolute resource root of a command.

    Parameters
    ----------
    option : Path or None
        The value of ``--root``, relative to the current folder.

    Returns
    -------
    Path
        ``--root``, else ``CHROMATA_ROOT``, else the nearest ancestor of the current folder that
        holds a configuration file, else the current folder.
    """
    if option is not None:
        return option.resolve()
    named = os.environ.get(ROOT_ENV, "").strip()
    if named:
        return Path(named).resolve()
    current = Path.cwd().resolve()
    for directory in (current, *current.parents):
        if _holds_settings(directory):
            return directory
    return current


def locate_settings(root: Path) -> Path | None:
    """
    Return the configuration file below ``root``, or ``None`` when the root holds none.

    Raises
    ------
    ManifestError
        If the root holds both ``config/tools/chromata.yml`` and ``chromata.yml``.
    """
    found = [root / location for location in SETTINGS_LOCATIONS if (root / location).is_file()]
    if len(found) > 1:
        raise ManifestError(
            f"two configuration files compete: {found[0]} and {found[1]}; keep one"
        )
    return found[0] if found else None
