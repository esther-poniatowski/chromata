"""
The consumer's specification of its palette: acceptance tests and recolouring rows.

A consumer writes one TOML file; nothing about any particular document lives in this package. The
file holds two tables, each optional::

    [tests]
    ground = "posterbg"          # the page ground, against which marks need contrast
    de_floor = 0.15              # minimal OKLab distance between two tokens a reader must tell apart
    contrast_floor = 3.0         # minimal WCAG contrast of a graphical mark on the ground
    marks = ["comp1", ...]       # tokens bound by the contrast floor
    fills = ["surface", ...]     # washes and grounds: reported, exempt from the contrast floor

    [tests.groups]               # sets whose members can share one figure
    "components" = ["comp1", "comp2"]

    [[tests.exempt]]             # pairs whose distinction rides on a non-colour channel
    pair = ["outplane", "outplaneannot"]
    channel = "line style"

    [[tests.accepted]]           # marks accepted under the contrast floor, each with its reason
    token = "inputlight"
    reason = "drawn only inside framed cell grids"

    [recolour]
    targets = ["comp1", "comp2"] # the two tokens the pictures are repainted into

    [[recolour.rows]]            # pictures made of two colours: two singles, then their mixture
    name = "vision"
    strategy = "unmix"           # or "rotate"
    files = ["a.png", "b.png", "a-plus-b.png"]
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

Strategy = Literal["unmix", "rotate"]


class SpecError(ValueError):
    """Raised when a specification file is malformed."""


@dataclass(frozen=True)
class AcceptanceTests:
    """The three acceptance tests of a palette, and the tokens each one binds."""

    ground: str
    de_floor: float = 0.15
    contrast_floor: float = 3.0
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    exempt: dict[frozenset[str], str] = field(default_factory=dict)
    accepted: dict[str, str] = field(default_factory=dict)
    marks: tuple[str, ...] = ()
    fills: tuple[str, ...] = ()

    def named_tokens(self) -> set[str]:
        """Every token the tests mention, for reporting tokens absent from the palette."""
        named = {t for g in self.groups.values() for t in g} | set(self.marks) | set(self.fills)
        return named | {self.ground}


@dataclass(frozen=True)
class RecolourRow:
    """Two single-colour pictures and their mixture, repainted by one strategy."""

    name: str
    strategy: Strategy
    first: str
    second: str
    mixture: str


@dataclass(frozen=True)
class RecolourPlan:
    """The two target tokens and the rows of pictures to repaint into them."""

    targets: tuple[str, str]
    rows: tuple[RecolourRow, ...]


@dataclass(frozen=True)
class PaletteSpec:
    """A consumer's specification; either part may be absent."""

    tests: AcceptanceTests | None
    recolour: RecolourPlan | None


def _strings(value: object, where: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise SpecError(f"{where}: expected a list of token names")
    return tuple(value)


def _tests(table: dict[str, object]) -> AcceptanceTests:
    ground = table.get("ground")
    if not isinstance(ground, str):
        raise SpecError("[tests] ground: expected a token name")
    groups_raw = table.get("groups", {})
    if not isinstance(groups_raw, dict):
        raise SpecError("[tests.groups]: expected a table of token lists")
    groups = {str(k): _strings(v, f"[tests.groups] {k}") for k, v in groups_raw.items()}
    exempt: dict[frozenset[str], str] = {}
    exempt_raw = table.get("exempt", [])
    if not isinstance(exempt_raw, list):
        raise SpecError("[[tests.exempt]]: expected an array of tables")
    for entry in exempt_raw:
        if not isinstance(entry, dict):
            raise SpecError("[[tests.exempt]]: expected a table with `pair' and `channel'")
        pair = _strings(entry.get("pair"), "[[tests.exempt]] pair")
        channel = entry.get("channel")
        if len(pair) != 2 or not isinstance(channel, str):
            raise SpecError("[[tests.exempt]]: `pair' takes two tokens and `channel' names the channel")
        exempt[frozenset(pair)] = channel
    accepted: dict[str, str] = {}
    accepted_raw = table.get("accepted", [])
    if not isinstance(accepted_raw, list):
        raise SpecError("[[tests.accepted]]: expected an array of tables")
    for entry in accepted_raw:
        if not isinstance(entry, dict):
            raise SpecError("[[tests.accepted]]: expected a table with `token' and `reason'")
        token, reason = entry.get("token"), entry.get("reason")
        if not isinstance(token, str) or not isinstance(reason, str) or not reason.strip():
            raise SpecError("[[tests.accepted]]: `token' names one mark and `reason' states why")
        accepted[token] = reason
    return AcceptanceTests(
        ground=ground,
        de_floor=float(table.get("de_floor", 0.15)),  # type: ignore[arg-type]
        contrast_floor=float(table.get("contrast_floor", 3.0)),  # type: ignore[arg-type]
        groups=groups,
        exempt=exempt,
        accepted=accepted,
        marks=_strings(table.get("marks", []), "[tests] marks"),
        fills=_strings(table.get("fills", []), "[tests] fills"),
    )


def _recolour(table: dict[str, object]) -> RecolourPlan:
    targets = _strings(table.get("targets"), "[recolour] targets")
    if len(targets) != 2:
        raise SpecError("[recolour] targets: expected exactly two tokens")
    rows: list[RecolourRow] = []
    rows_raw = table.get("rows", [])
    if not isinstance(rows_raw, list):
        raise SpecError("[[recolour.rows]]: expected an array of tables")
    for entry in rows_raw:
        if not isinstance(entry, dict):
            raise SpecError("[[recolour.rows]]: expected a table")
        strategy = entry.get("strategy")
        if strategy not in ("unmix", "rotate"):
            raise SpecError(f"[[recolour.rows]] strategy: expected `unmix' or `rotate', got {strategy!r}")
        files = _strings(entry.get("files"), "[[recolour.rows]] files")
        if len(files) != 3:
            raise SpecError("[[recolour.rows]] files: expected two singles, then their mixture")
        rows.append(RecolourRow(str(entry.get("name", files[2])), strategy, *files))
    return RecolourPlan((targets[0], targets[1]), tuple(rows))


def load_spec(path: Path) -> PaletteSpec:
    """
    Load a specification file.

    Parameters
    ----------
    path : Path
        A TOML file in the format of the module docstring.

    Returns
    -------
    PaletteSpec
        The parsed specification.

    Raises
    ------
    SpecError
        If the file is missing or malformed.
    """
    if not path.exists():
        raise SpecError(f"no such specification: {path}")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    tests = data.get("tests")
    recolour = data.get("recolour")
    return PaletteSpec(
        tests=_tests(tests) if isinstance(tests, dict) else None,
        recolour=_recolour(recolour) if isinstance(recolour, dict) else None,
    )
