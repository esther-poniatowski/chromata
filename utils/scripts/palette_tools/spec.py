"""
A palette file: its tokens, roles, modes, CSS names, acceptance tests and recolouring rows.

A consumer writes one ``palette.yml`` under the format of ``utils/schemas/palette.schema.yaml``;
nothing about any particular document lives in this package. Loading a file validates it against
the schema, then checks what the schema cannot express: every name resolves, no name is declared
twice, the palette holds only what its level admits, and no name outside a hue library states a
hue unless the file declares ``legacy_hue_names``.

Three levels separate the colours from their uses. A hue library declares the values, named after
their hue. A house style binds the elements of the page to hues, and a concept binding binds the
concepts of one project to hues; both hold roles, whose names state a use.

A palette may extend another one, whose tokens and roles it may then name. Its values are the
values of the extended palette, then its own tokens, then the overrides of a candidate scheme, and
finally its roles, which copy the values in force when they are bound, as LaTeX does. A mode
overrides a token before the roles are bound, and a role after them.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

import yaml
from jsonschema import Draft202012Validator

from palette_tools.colour import hex_to_srgb, srgb_to_hex
from vault_paths import DEFAULT_ROOT, PALETTE_SCHEMA

Strategy = Literal["unmix", "rotate"]

#: Order of the rungs of a ladder, from the darkest to the lightest.
RUNGS: tuple[str, ...] = ("deep", "core", "bright", "light", "pale")

#: Colours that LaTeX defines without a palette, and that a role may bind.
BUILTINS: dict[str, str] = {"black": "000000", "white": "FFFFFF"}

#: Words naming a hue. A token or role containing one is named after its colour, not its use.
HUE_WORDS: tuple[str, ...] = (
    "red", "green", "blue", "orange", "yellow", "purple", "violet", "magenta", "cyan", "teal",
    "brown", "gray", "grey", "gold", "olive", "amber", "indigo", "terra", "pink", "salmon",
    "turquoise", "brick", "crimson", "navy", "maroon", "lime", "beige",
)


class SpecError(ValueError):
    """Raised when a palette file is missing, malformed, or inconsistent."""


@dataclass(frozen=True)
class AcceptanceTests:
    """The acceptance tests of a palette, and the tokens each one binds."""

    ground: str
    de_floor: float = 0.15
    contrast_floor: float = 3.0
    groups: dict[str, tuple[str, ...]] = field(default_factory=dict)
    exempt: dict[frozenset[str], str] = field(default_factory=dict)
    accepted: dict[str, str] = field(default_factory=dict)
    marks: tuple[str, ...] = ()
    fills: tuple[str, ...] = ()
    #: ``token -> (pole, rung index)``, for the tokens placed on a ladder.
    ladder: dict[str, tuple[str, int]] = field(default_factory=dict)
    #: ``(mark, ground)`` pairs, each bound by the contrast floor on its own ground.
    pairs: tuple[tuple[str, str], ...] = ()

    def named_tokens(self) -> set[str]:
        """Every token the tests mention, for reporting tokens absent from the palette."""
        named = {t for g in self.groups.values() for t in g} | set(self.marks) | set(self.fills)
        return named | {self.ground} | {t for pair in self.pairs for t in pair}


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
class Token:
    """One colour value, with the use it marks."""

    name: str
    layer: str
    value: str
    use: str
    note: str | None = None
    pole: str | None = None
    rung: str | None = None
    contrast: str | None = None
    below_floor: str | None = None


@dataclass(frozen=True)
class Layer:
    """A set of tokens retuned together."""

    name: str
    gloss: str
    note: str | None
    tokens: tuple[Token, ...]


@dataclass(frozen=True)
class Role:
    """A name used by call sites, bound to a token, a role or a LaTeX colour, possibly tinted."""

    name: str
    of: str
    use: str
    tint: int | None = None
    note: str | None = None
    contrast: str | None = None
    below_floor: str | None = None


@dataclass(frozen=True)
class PaletteSpec:
    """A loaded palette file."""

    path: Path
    layers: tuple[Layer, ...]
    roles: tuple[Role, ...] = ()
    modes: dict[str, dict[str, str]] = field(default_factory=dict)
    mode_glosses: dict[str, str] = field(default_factory=dict)
    mode_tests: dict[str, AcceptanceTests] = field(default_factory=dict)
    css: dict[str, str] = field(default_factory=dict)
    tests: AcceptanceTests | None = None
    recolour: RecolourPlan | None = None
    base: PaletteSpec | None = None
    legacy_hue_names: str | None = None
    level: str | None = None

    def tokens(self) -> dict[str, Token]:
        """The tokens of this file, by name, in load order."""
        return {t.name: t for layer in self.layers for t in layer.tokens}

    def all_tokens(self) -> dict[str, Token]:
        """The tokens of this file and of the palettes it extends, by name."""
        return {**(self.base.all_tokens() if self.base else {}), **self.tokens()}

    def all_roles(self) -> dict[str, Role]:
        """The roles of this file and of the palettes it extends, by name."""
        return {**(self.base.all_roles() if self.base else {}), **{r.name: r for r in self.roles}}

    def resolve(self, name: str) -> Token | None:
        """The token that a name reaches through its chain of roles, if any."""
        tokens, roles = self.all_tokens(), self.all_roles()
        seen: set[str] = set()
        while name in roles and name not in seen:
            seen.add(name)
            name = roles[name].of
        return tokens.get(name)

    def has_mode(self, mode: str) -> bool:
        """Whether this file or a palette it extends declares the mode."""
        return mode in self.modes or (self.base is not None and self.base.has_mode(mode))

    def tests_for(self, mode: str | None) -> AcceptanceTests | None:
        """The tests of the base rendering, or of a mode declared here or in an extended palette."""
        if mode is None:
            return self.tests
        if mode in self.mode_tests:
            return self.mode_tests[mode]
        return self.base.tests_for(mode) if self.base else None

    def names(self) -> set[str]:
        """Every token and role name that this file and the palettes it extends define."""
        own = set(self.tokens()) | {r.name for r in self.roles}
        return own | (self.base.names() if self.base else set())

    def token_values(self, mode: str | None = None) -> dict[str, str]:
        """``token -> RRGGBB`` before the roles: the extended palette first, then this file."""
        values = self.base.values(mode) if self.base else {}
        values.update({name: token.value for name, token in self.tokens().items()})
        if mode is not None:
            values.update({n: v for n, v in self.modes.get(mode, {}).items() if n in self.tokens()})
        return values

    def bind_roles(self, values: dict[str, str]) -> dict[str, str]:
        """Bind the roles of this file onto ``values``, in load order, and return the result."""
        out = dict(values)
        for role in self.roles:
            source = out.get(role.of, BUILTINS.get(role.of))
            if source is None:
                raise SpecError(f"{self.path}: role `{role.name}' binds unknown `{role.of}'")
            if role.tint is None:
                out[role.name] = source
            else:
                frac = role.tint / 100.0
                r, g, b = hex_to_srgb(source)
                out[role.name] = srgb_to_hex(tuple(c * frac + (1 - frac) for c in (r, g, b)))
        return out

    def override_roles(self, values: dict[str, str], mode: str | None) -> dict[str, str]:
        """Apply the overrides of the roles that this file declares for a mode, after binding."""
        out = dict(values)
        if mode is not None:
            out.update({n: v for n, v in self.modes.get(mode, {}).items() if n not in self.tokens()})
        return out

    def values(self, mode: str | None = None) -> dict[str, str]:
        """``name -> RRGGBB`` for every token and role, in the given mode."""
        return self.override_roles(self.bind_roles(self.token_values(mode)), mode)


def _schema_validator() -> Draft202012Validator:
    with (DEFAULT_ROOT / PALETTE_SCHEMA).open(encoding="utf-8") as handle:
        return Draft202012Validator(yaml.safe_load(handle))


def _hue_word(name: str) -> str | None:
    lowered = name.lower()
    return next((word for word in HUE_WORDS if word in lowered), None)


def _tests(data: dict[str, Any], members: dict[str, Token | Role], spec: PaletteSpec,
           accepted: dict[str, str] | None = None) -> AcceptanceTests:
    """
    The tests of one rendering.

    ``members`` are the tokens and roles bound as marks or fills by their contrast key. The ladder
    of a name is the pole and rung of the token that it reaches through its roles.
    """
    if accepted is None:
        accepted = {m.name: m.below_floor for m in members.values() if m.below_floor}
    ladder: dict[str, tuple[str, int]] = {}
    for name in [*spec.all_tokens(), *spec.all_roles()]:
        token = spec.resolve(name)
        if token is not None and token.pole and token.rung:
            ladder[name] = (token.pole, RUNGS.index(token.rung))
    return AcceptanceTests(
        ground=data["ground"],
        de_floor=float(data.get("de_floor", 0.15)),
        contrast_floor=float(data.get("contrast_floor", 3.0)),
        groups={str(k): tuple(v) for k, v in data.get("groups", {}).items()},
        exempt={frozenset(e["pair"]): e["channel"] for e in data.get("exempt", [])},
        pairs=tuple((p["mark"], p["ground"]) for p in data.get("pairs", [])),
        accepted=accepted,
        marks=tuple(m.name for m in members.values() if m.contrast == "mark"),
        fills=tuple(m.name for m in members.values() if m.contrast == "fill"),
        ladder=ladder,
    )


def _recolour(data: dict[str, Any]) -> RecolourPlan:
    rows = tuple(RecolourRow(row["name"], row["strategy"], *row["files"]) for row in data["rows"])
    return RecolourPlan((data["targets"][0], data["targets"][1]), rows)


def _consistency(spec: PaletteSpec, data: dict[str, Any]) -> list[str]:
    """The checks that the schema cannot express."""
    problems: list[str] = []
    seen: dict[str, str] = {}
    inherited = spec.base.names() if spec.base else set()
    for layer in spec.layers:
        for token in layer.tokens:
            if token.name in seen or token.name in inherited:
                problems.append(f"token `{token.name}' is declared twice")
            seen[token.name] = layer.name
    for role in spec.roles:
        if role.name in seen or role.name in inherited:
            problems.append(f"role `{role.name}' reuses a declared name")
        if role.of not in seen and role.of not in inherited and role.of not in BUILTINS:
            problems.append(f"role `{role.name}' binds `{role.of}', which is not declared before it")
        seen[role.name] = "roles"
    names = spec.names()
    for mode, values in spec.modes.items():
        problems += [f"mode `{mode}' overrides undeclared `{n}'" for n in values if n not in names]
    problems += [f"css `--{k}' binds undeclared `{v}'" for k, v in spec.css.items() if v not in names]
    for label, tests in [("tests", spec.tests),
                         *((f"tests of mode `{m}'", t) for m, t in spec.mode_tests.items())]:
        if tests is None:
            continue
        named = tests.named_tokens() | {t for pair in tests.exempt for t in pair}
        named |= set(tests.accepted)
        problems += [f"{label} name undeclared `{n}'" for n in sorted(named - names)]
    if spec.recolour is not None:
        problems += [f"recolour targets undeclared `{n}'"
                     for n in spec.recolour.targets if n not in names]
    if spec.level == "hues":
        if spec.roles or spec.css or spec.modes or spec.tests or spec.recolour:
            problems.append("a hue library declares values alone: no roles, CSS, modes or tests")
    elif spec.level in ("style", "concepts") and spec.layers:
        problems.append(f"a {spec.level} palette binds roles to hues and declares no value")
    if spec.legacy_hue_names is None and spec.level != "hues":
        for name in [*spec.tokens(), *(r.name for r in spec.roles)]:
            if (word := _hue_word(name)) is not None:
                problems.append(f"`{name}' is named after its hue ({word}): name the use it marks")
    return problems


def load_spec(path: Path, root: Path = DEFAULT_ROOT) -> PaletteSpec:
    """
    Load and check a palette file.

    Parameters
    ----------
    path : Path
        A ``palette.yml`` file.
    root : Path, optional
        The vault root, against which ``extends`` is resolved.

    Returns
    -------
    PaletteSpec
        The loaded palette, with the palette it extends.

    Raises
    ------
    SpecError
        If the file is missing, breaks the schema, or names something undeclared.
    """
    if not path.exists():
        raise SpecError(f"no such palette: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    errors = sorted(_schema_validator().iter_errors(data), key=lambda e: list(e.absolute_path))
    if errors:
        details = "; ".join(f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}"
                            for e in errors)
        raise SpecError(f"{path}: schema violation: {details}")
    base = load_spec(root / data["extends"], root) if "extends" in data else None
    layers = tuple(
        Layer(name, layer["gloss"], layer.get("note"), tuple(
            Token(token_name, name, t["value"], t["use"], t.get("note"), t.get("pole"),
                  t.get("rung"), t.get("contrast"), t.get("below_floor"))
            for token_name, t in layer["tokens"].items()))
        for name, layer in data.get("layers", {}).items())
    modes = data.get("modes", {})
    bare = PaletteSpec(
        path=path,
        layers=layers,
        roles=tuple(Role(name, r["of"], r["use"], r.get("tint"), r.get("note"), r.get("contrast"),
                         r.get("below_floor"))
                    for name, r in data.get("roles", {}).items()),
        modes={name: dict(mode["values"]) for name, mode in modes.items()},
        mode_glosses={name: mode["gloss"] for name, mode in modes.items()},
        css=dict(data.get("css", {})),
        recolour=_recolour(data["recolour"]) if "recolour" in data else None,
        base=base,
        legacy_hue_names=data.get("legacy_hue_names"),
        level=data.get("level"),
    )
    own: dict[str, Token | Role] = {**bare.tokens(), **{r.name: r for r in bare.roles}}
    chain: dict[str, Token | Role] = {**bare.all_tokens(), **bare.all_roles()}
    spec = replace(
        bare,
        tests=_tests(data["tests"], own, bare) if "tests" in data else None,
        mode_tests={
            name: _tests(mode["tests"], {n: chain[n] for n in mode["values"] if n in chain}, bare,
                         {a["token"]: a["reason"] for a in mode["tests"].get("accepted", [])})
            for name, mode in modes.items() if "tests" in mode},
    )
    problems = _consistency(spec, data)
    if problems:
        raise SpecError(f"{path}: " + "; ".join(problems))
    return spec
