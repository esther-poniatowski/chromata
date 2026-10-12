"""
Reading a palette out of LaTeX sources.

Understands ``\\definecolor{n}{HTML}{HEX}``, ``\\colorlet{n}{m}`` and the tint-toward-white form
``\\colorlet{n}{m!NN}``. Commented-out lines are ignored, so a retired token stays retired.
"""

from __future__ import annotations

import re
from pathlib import Path

from palette_tools.colour import hex_to_srgb, srgb_to_hex

DEFINE_RE = re.compile(r"^\s*\\definecolor\{(\w+)\}\{HTML\}\{([0-9A-Fa-f]{6})\}")
LET_RE = re.compile(r"^\s*\\colorlet\{(\w+)\}\{(\w+)(?:!(\d+))?\}")


class PaletteSourceError(FileNotFoundError):
    """Raised when a palette source file does not exist."""


def parse_palette(text: str, palette: dict[str, str] | None = None) -> dict[str, str]:
    """
    Apply the colour definitions of one LaTeX source to a palette.

    Parameters
    ----------
    text : str
        The LaTeX source.
    palette : dict[str, str], optional
        Tokens already defined; a later definition overrides an earlier one. A new dictionary is
        returned, so the argument is never modified.

    Returns
    -------
    dict[str, str]
        ``token -> RRGGBB``.

    Examples
    --------
    >>> parse_palette("\\\\definecolor{a}{HTML}{ff0000}\\n\\\\colorlet{b}{a!50}")
    {'a': 'FF0000', 'b': 'FF8080'}
    """
    out = dict(palette or {})
    for line in text.splitlines():
        if line.lstrip().startswith("%"):
            continue
        if (m := DEFINE_RE.match(line)) is not None:
            out[m.group(1)] = m.group(2).upper()
        elif (m := LET_RE.match(line)) is not None:
            source = out.get(m.group(2))
            if source is None:
                continue
            if m.group(3) is None:
                out[m.group(1)] = source
            else:
                frac = int(m.group(3)) / 100.0
                r, g, b = hex_to_srgb(source)
                out[m.group(1)] = srgb_to_hex(
                    (r * frac + (1 - frac), g * frac + (1 - frac), b * frac + (1 - frac))
                )
    return out


def read_palette(*paths: Path) -> dict[str, str]:
    """
    Collect ``token -> RRGGBB`` from LaTeX sources, applying each file's definitions in order.

    Parameters
    ----------
    *paths : Path
        Palette sources, in load order (for instance values, then roles).

    Returns
    -------
    dict[str, str]
        ``token -> RRGGBB``.

    Raises
    ------
    PaletteSourceError
        If a source does not exist.
    """
    palette: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            raise PaletteSourceError(f"no such palette source: {path}")
        palette = parse_palette(path.read_text(encoding="utf-8"), palette)
    return palette
