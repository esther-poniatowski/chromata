"""
The files generated from a palette: its LaTeX value layer, its LaTeX role layer, and its CSS block.

Every generated text states its source and its generator, so that an edit is made in the palette
and never in the output. By default, the LaTeX layers are written beside the palette file as
``colors-values.tex`` and ``colors-roles.tex``. A CSS projection is returned as one standalone,
marked block for the explicit target selected by the consumer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from chromata.spec import BUILTINS, PaletteSpec

#: Names of the generated LaTeX layers, beside the palette file.
VALUES_FILE = "colors-values.tex"
ROLES_FILE = "colors-roles.tex"

#: Media query of each mode in CSS.
MEDIA = {"dark": "prefers-color-scheme: dark"}

GENERATOR = "chromata-build"

_TEX_NAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9@_-]*$")
_TEX_PREFIX_RE = re.compile(r"^(?:[A-Za-z][A-Za-z0-9@_-]*)?$")


class ProjectionError(ValueError):
    """Raised when a TeX projection would emit an unsafe or ambiguous interface."""


@dataclass(frozen=True, init=False)
class TeXProjection:
    """A validated mapping from palette names to TeX colour names."""

    values_prefix: str
    roles_prefix: str
    names: Mapping[str, str]
    logical_names: frozenset[str]
    token_names: frozenset[str]
    role_names: frozenset[str]

    @classmethod
    def for_spec(
        cls,
        spec: PaletteSpec,
        *,
        values_prefix: str = "",
        roles_prefix: str = "",
        names: Mapping[str, str] | None = None,
    ) -> TeXProjection:
        """Validate and construct the TeX interface of ``spec``."""
        if not _TEX_PREFIX_RE.fullmatch(values_prefix):
            raise ProjectionError("value prefix must contain only letters, digits, @, _, or -")
        if not _TEX_PREFIX_RE.fullmatch(roles_prefix):
            raise ProjectionError("role prefix must contain only letters, digits, @, _, or -")
        mapped = dict(names or {})
        unsafe = {
            source: target
            for source, target in mapped.items()
            if not _TEX_NAME_RE.fullmatch(target)
        }
        if unsafe:
            raise ProjectionError(f"unsafe TeX names: {unsafe}")
        unknown = set(mapped) - spec.names()
        if unknown:
            raise ProjectionError(f"TeX names map unknown palette names: {sorted(unknown)}")

        token_names = frozenset(spec.all_tokens())
        role_names = frozenset(spec.all_roles())
        logical_names = token_names | role_names
        emitted: dict[str, list[str]] = {}
        for logical in token_names:
            emitted.setdefault(values_prefix + mapped.get(logical, logical), []).append(logical)
        for logical in role_names:
            emitted.setdefault(roles_prefix + mapped.get(logical, logical), []).append(logical)
        collisions = {
            output: logicals for output, logicals in emitted.items() if len(logicals) > 1
        }
        if collisions:
            raise ProjectionError(f"TeX name collisions: {collisions}")
        replaced = sorted(set(emitted) & set(BUILTINS))
        if replaced:
            raise ProjectionError(f"TeX names replace built-in colours: {replaced}")
        projection = object.__new__(cls)
        object.__setattr__(projection, "values_prefix", values_prefix)
        object.__setattr__(projection, "roles_prefix", roles_prefix)
        object.__setattr__(projection, "names", MappingProxyType(mapped))
        object.__setattr__(projection, "logical_names", logical_names)
        object.__setattr__(projection, "token_names", token_names)
        object.__setattr__(projection, "role_names", role_names)
        return projection

    def require(self, spec: PaletteSpec) -> None:
        """Reject use with a specification outside the validated logical interface."""
        tokens = frozenset(spec.all_tokens())
        roles = frozenset(spec.all_roles())
        if tokens != self.token_names or roles != self.role_names:
            raise ProjectionError("projection was validated for a different token/role partition")

    def value_name(self, name: str) -> str:
        """Return the TeX name of a value token."""
        return self.values_prefix + self.names.get(name, name)

    def role_name(self, name: str) -> str:
        """Return the TeX name of a role."""
        return self.roles_prefix + self.names.get(name, name)

    def reference_name(self, name: str) -> str:
        """Return the TeX name of a built-in, value token, or role reference."""
        if name in BUILTINS:
            return name
        return self.value_name(name) if name in self.token_names else self.role_name(name)


def _header(source: str, layer: str) -> list[str]:
    return [
        f"% Generated from {source} by {GENERATOR}.",
        "% Edit the palette specification, then regenerate this file.",
        f"% {layer}",
    ]


def latex_values(
    spec: PaletteSpec,
    source: str,
    projection: TeXProjection | None = None,
) -> str:
    """
    The ``\\definecolor`` layer of a palette.

    Parameters
    ----------
    spec : PaletteSpec
        The palette.
    source : str
        The stable source label printed in the header.
    projection : TeXProjection | None
        The validated TeX interface. The default preserves the palette names.

    Returns
    -------
    str
        The LaTeX source, one ``\\definecolor`` per token, grouped by layer.
    """
    active = projection or TeXProjection.for_spec(spec)
    active.require(spec)
    lines = _header(source, "The value of each token, grouped by layer.")
    for layer in spec.layers:
        lines += ["", f"% ----- {layer.name}: {layer.gloss}"]
        output_names = [active.value_name(token.name) for token in layer.tokens]
        width = max(len(name) for name in output_names)
        for token, name in zip(layer.tokens, output_names):
            use = f"{token.rung} -- {token.use}" if token.rung else token.use
            lines.append(f"\\definecolor{{{name}}}{{HTML}}{{{token.value}}}"
                         f"{' ' * (width - len(name))} % {use}")
    return "\n".join(lines) + "\n"


def latex_roles(
    spec: PaletteSpec,
    source: str,
    *,
    projection: TeXProjection | None = None,
) -> str:
    """
    The ``\\colorlet`` layer of a palette, to be loaded after its value layer.

    Parameters
    ----------
    spec : PaletteSpec
        The palette, which binds at least one role.
    source : str
        The stable source label printed in the header.
    projection : TeXProjection | None
        The validated TeX interface. The default preserves the palette names.

    Returns
    -------
    str
        The LaTeX source, one ``\\colorlet`` per role, in load order.
    """
    active = projection or TeXProjection.for_spec(spec)
    active.require(spec)
    lines = _header(source, "The token bound to each role. Load it after the values: "
                          "\\colorlet copies a value when it is read.")
    lines.append("")
    output_names = [active.role_name(role.name) for role in spec.roles]
    targets = []
    for role in spec.roles:
        target = active.reference_name(role.of)
        targets.append(f"{target}!{role.tint}" if role.tint else target)
    width = max(len(name) + len(target) for name, target in zip(output_names, targets))
    for role, name, target in zip(spec.roles, output_names, targets):
        pad = " " * (width - len(name) - len(target))
        lines.append(f"\\colorlet{{{name}}}{{{target}}}{pad} % {role.use}")
    return "\n".join(lines) + "\n"


def css_block(spec: PaletteSpec, source: str, indent: str) -> str:
    """
    The CSS custom properties of a palette, with one media block per mode.

    Parameters
    ----------
    spec : PaletteSpec
        The palette, which declares at least one CSS name.
    source : str
        The path of the palette printed in the opening marker.
    indent : str
        The indentation of the opening marker, applied to every line.

    Returns
    -------
    str
        The block, from its opening marker to its closing marker, without a final newline.
    """
    base = spec.values()
    lines = [f"/* palette: {source} -- generated by {GENERATOR}; edit the palette */", ":root {"]
    lines += [f"  --{name}: #{base[target]};" for name, target in spec.css.items()]
    lines.append("}")
    for mode, query in MEDIA.items():
        if mode not in spec.modes:
            continue
        shifted = spec.values(mode)
        changed = [(n, t) for n, t in spec.css.items() if shifted[t] != base[t]]
        lines += [f"@media ({query}) {{", "  :root {"]
        lines += [f"    --{name}: #{shifted[target]};" for name, target in changed]
        lines += ["  }", "}"]
    lines.append("/* palette: end */")
    return "\n".join(indent + line for line in lines)


def outputs(
    spec: PaletteSpec,
    root: Path,
    *,
    values_target: Path | None = None,
    roles_target: Path | None = None,
    projection: TeXProjection | None = None,
    source_label: str | None = None,
) -> dict[Path, str]:
    """
    The LaTeX layers generated from a palette, by output path.

    Parameters
    ----------
    spec : PaletteSpec
        The palette.
    root : Path
        The resource root against which header paths are written.
    values_target : Path | None
        The value-layer destination. The default is beside the palette.
    roles_target : Path | None
        The role-layer destination. The default is beside the palette.
    projection : TeXProjection | None
        The validated TeX interface. The default preserves the palette names.
    source_label : str | None
        The stable header label. The default is the palette path relative to ``root``.

    Returns
    -------
    dict[Path, str]
        The text of each generated file.
    """
    folder = spec.path.parent
    source = source_label or display_path(spec.path, root)
    active = projection or TeXProjection.for_spec(spec)
    active.require(spec)
    out: dict[Path, str] = {}
    if spec.layers:
        values = values_target or folder / VALUES_FILE
        out[values] = latex_values(spec, source, active)
    if spec.roles:
        roles = roles_target or folder / ROLES_FILE
        out[roles] = latex_roles(
            spec,
            source,
            projection=active,
        )
    return out


def display_path(path: Path, root: Path) -> str:
    """Return a stable root-relative label, rejecting a machine-specific absolute fallback."""
    return path.resolve().relative_to(root.resolve()).as_posix()
