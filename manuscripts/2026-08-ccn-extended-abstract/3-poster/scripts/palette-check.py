#!/usr/bin/env python3
"""Measure a poster colour scheme against the palette's own acceptance tests.

The poster's colour doctrine (``parts/colors-values.tex``) states three tests that a token must
pass, and until now all three were applied by eye and recorded in prose. Every additional scheme
multiplies that manual work, which is exactly the point at which a hand check stops being done.
This script applies them mechanically to any scheme:

1. **Categorical separation.** Two colours a reader must tell apart need dE >= 0.15 in OKLab.
   Below that they are not distinct categories, whatever they look like side by side.
2. **Mark contrast.** A graphical mark needs >= 3:1 luminance contrast on the page ground. Fills
   and washes are exempt and must carry a saturated stroke instead.
3. **Non-colour redundancy.** Test 1 is repeated under simulated colour-vision deficiency
   (protanopia, deuteranopia, tritanopia) and under grayscale. A pair that separates only for
   trichromats is a pair whose distinction is carried by hue alone, which the poster does not allow
   to be load-bearing.

Colour science, all standard and dependency-free:

* OKLab (Ottosson 2020) for perceptual distance -- the space the doctrine is already written in.
* WCAG 2.1 relative luminance for contrast.
* Machado, Oliveira & Fernandes (2009) severity-1.0 matrices for the three dichromacies, applied in
  linear RGB.

Usage, from the poster directory (never from the base conda environment)::

    conda run -n geonexus python scripts/palette-check.py                  # the base scheme
    conda run -n geonexus python scripts/palette-check.py neutral-chrome   # a named scheme
    conda run -n geonexus python scripts/palette-check.py --grey-for chromecore

The exit status is 1 if any *binding* check fails, so the script can gate a build.
"""

from __future__ import annotations

import argparse
import math
import re
import sys
from itertools import combinations
from pathlib import Path

# --------------------------------------------------------------------------------------------------
# Colour conversion
# --------------------------------------------------------------------------------------------------

RGB = tuple[float, float, float]
Lab = tuple[float, float, float]


def hex_to_srgb(value: str) -> RGB:
    """Convert ``RRGGBB`` to sRGB channels in [0, 1].

    >>> hex_to_srgb("FFFFFF")
    (1.0, 1.0, 1.0)
    """
    v = value.lstrip("#")
    return tuple(int(v[i : i + 2], 16) / 255.0 for i in (0, 2, 4))  # type: ignore[return-value]


def srgb_to_hex(rgb: RGB) -> str:
    """Convert sRGB channels in [0, 1] to an uppercase ``RRGGBB`` string.

    >>> srgb_to_hex((1.0, 1.0, 1.0))
    'FFFFFF'
    """
    return "".join(f"{round(min(1.0, max(0.0, c)) * 255):02X}" for c in rgb)


def to_linear(rgb: RGB) -> RGB:
    """Undo the sRGB transfer function."""

    def f(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (f(rgb[0]), f(rgb[1]), f(rgb[2]))


def from_linear(rgb: RGB) -> RGB:
    """Apply the sRGB transfer function."""

    def f(c: float) -> float:
        c = min(1.0, max(0.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    return (f(rgb[0]), f(rgb[1]), f(rgb[2]))


def linear_to_oklab(rgb: RGB) -> Lab:
    """Convert linear RGB to OKLab (Ottosson 2020)."""
    r, g, b = rgb
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (l, m, s))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab(hex_value: str) -> Lab:
    """OKLab coordinates of an ``RRGGBB`` colour."""
    return linear_to_oklab(to_linear(hex_to_srgb(hex_value)))


def delta_e(a: Lab, b: Lab) -> float:
    """Euclidean OKLab distance -- the doctrine's dE."""
    return math.dist(a, b)


def luminance(hex_value: str) -> float:
    """WCAG relative luminance."""
    r, g, b = to_linear(hex_to_srgb(hex_value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """WCAG contrast ratio between two ``RRGGBB`` colours.

    >>> round(contrast("FFFFFF", "000000"), 1)
    21.0
    """
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def grey_matching(hex_value: str) -> str:
    """The neutral grey with the same OKLab lightness as ``hex_value``.

    For a neutral the three OKLab cone responses are equal and the matrix rows sum to one, so
    ``L = v**(1/3)`` in linear RGB and the inversion is exact.

    >>> grey_matching("FFFFFF")
    'FFFFFF'
    """
    lightness = oklab(hex_value)[0]
    v = lightness**3
    return srgb_to_hex(from_linear((v, v, v)))


# --------------------------------------------------------------------------------------------------
# Colour-vision deficiency
# --------------------------------------------------------------------------------------------------

CVD_MATRICES: dict[str, tuple[RGB, RGB, RGB]] = {
    "protan": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
    "deutan": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "tritan": (
        (1.255528, -0.076749, -0.178779),
        (-0.078411, 0.930809, 0.147602),
        (0.004733, 0.691367, 0.303900),
    ),
}


def simulate(hex_value: str, mode: str) -> str:
    """Simulate a colour as seen under ``mode`` (``protan``/``deutan``/``tritan``/``grey``)."""
    lin = to_linear(hex_to_srgb(hex_value))
    if mode == "grey":
        y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
        out: RGB = (y, y, y)
    else:
        m = CVD_MATRICES[mode]
        out = tuple(sum(m[i][j] * lin[j] for j in range(3)) for i in range(3))  # type: ignore[assignment]
    return srgb_to_hex(from_linear(out))


VISION_MODES = ("normal", "protan", "deutan", "tritan", "grey")


# --------------------------------------------------------------------------------------------------
# Reading the palette out of the LaTeX source
# --------------------------------------------------------------------------------------------------

DEFINE_RE = re.compile(r"^\s*\\definecolor\{(\w+)\}\{HTML\}\{([0-9A-Fa-f]{6})\}")
LET_RE = re.compile(r"^\s*\\colorlet\{(\w+)\}\{(\w+)(?:!(\d+))?\}")


def read_palette(*paths: Path) -> dict[str, str]:
    """Collect ``token -> RRGGBB`` from LaTeX sources, applying each file's overrides in order.

    Understands ``\\definecolor{n}{HTML}{HEX}``, ``\\colorlet{n}{m}`` and the tint-toward-white form
    ``\\colorlet{n}{m!NN}``. Commented-out lines are ignored, which is what makes a retired token
    stay retired.
    """
    palette: dict[str, str] = {}
    for path in paths:
        if not path.exists():
            raise SystemExit(f"palette-check: no such file: {path}")
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.lstrip().startswith("%"):
                continue
            if (m := DEFINE_RE.match(line)) is not None:
                palette[m.group(1)] = m.group(2).upper()
            elif (m := LET_RE.match(line)) is not None:
                source = palette.get(m.group(2))
                if source is None:
                    continue
                if m.group(3) is None:
                    palette[m.group(1)] = source
                else:
                    frac = int(m.group(3)) / 100.0
                    rgb = hex_to_srgb(source)
                    palette[m.group(1)] = srgb_to_hex(tuple(c * frac + (1 - frac) for c in rgb))
    return palette


# --------------------------------------------------------------------------------------------------
# The acceptance tests, as the doctrine states them
# --------------------------------------------------------------------------------------------------

DE_FLOOR = 0.15
CONTRAST_FLOOR = 3.0

#: Sets whose members a reader must tell apart. Derived from the co-occurrence claims in
#: parts/colors-values.tex; a set here is a promise that these tokens can share one figure.
GROUPS: dict[str, tuple[str, ...]] = {
    "components, response and geometry": (
        "comp1", "comp2", "mixresponse", "outplane", "outplaneannot",
    ),
    "the two transformations (skipping a rung)": (
        "inputdeep", "inputbright", "recurdeep", "recurbright",
    ),
    "transformations against components": (
        "inputbright", "recurbright", "comp1", "comp2", "mixresponse",
    ),
    "the two models, and their neighbours": ("modelnet", "modeldn", "comp2"),
    "chrome against every semantic token": (
        "chromecore", "comp1", "comp2", "mixresponse", "inputbright", "recurbright", "modelnet",
    ),
}

#: Pairs whose distinction is deliberately carried by a NON-COLOUR channel, with the channel named.
#: These are not failures: the doctrine's own answer to a full hue circle is to spend a non-colour
#: channel instead. Naming the channel is what keeps the exemption honest -- an entry here is a claim
#: that can be checked in the render, not a way to silence a number.
EXEMPT: dict[frozenset[str], str] = {
    frozenset({"chromecore", "modelnet"}): "licensed: modelnet IS the chrome, in the model band only",
    frozenset({"outplane", "outplaneannot"}): "line style (solid normal vs dashed in-plane reference)",
}

#: Graphical marks: bound by the 3:1 floor on the page ground.
MARKS: tuple[str, ...] = (
    "comp1", "comp2", "mixresponse", "outplane", "outplaneannot",
    "inputdeep", "inputcore", "inputbright", "inputlight",
    "recurdeep", "recurcore", "recurbright", "recurlight",
    "modelnet", "modeldn", "chromecore", "chromedeep", "chromealt",
    "borderfunc", "texttertiary", "textsecondary", "textprimary",
)

#: Fills and washes: exempt from the contrast floor, and required to carry a saturated stroke.
#: `compplane' is here and not in MARKS: the components plane is a wash under the vectors, and it
#: carries `planeedge' as its stroke.
FILLS: tuple[str, ...] = (
    "inputpale", "recurpale", "netfill", "surface", "bordersubtle", "compplane",
)

GROUND = "posterbg"


def report(palette: dict[str, str], scheme: str) -> int:
    """Print the full report and return the number of binding failures."""
    failures = 0
    named = {t for g in GROUPS.values() for t in g} | set(MARKS) | set(FILLS) | {GROUND}
    missing = sorted(named - palette.keys())
    if missing:
        print(f"tokens named by the checker but absent from the palette: {', '.join(missing)}\n")

    print(f"=== scheme: {scheme} ===\n")

    print("--- token lightness and contrast on the page ground ---")
    print(f"{'token':<16}{'hex':>8}{'OKLab L':>10}{'chroma':>9}{'on bg':>9}")
    for token in [GROUND, *MARKS, *FILLS]:
        if token not in palette:
            continue
        value = palette[token]
        lightness, a, b = oklab(value)
        ratio = contrast(value, palette[GROUND])
        flag = ""
        if token in MARKS and ratio < CONTRAST_FLOOR:
            flag = "  << under 3:1"
            failures += 1
        print(
            f"{token:<16}{value:>8}{lightness:>10.3f}{math.hypot(a, b):>9.3f}{ratio:>8.2f}:1{flag}"
        )

    # A pair may sit in more than one group (a token can have several co-occurrence claims). Count
    # each failing pair ONCE, or the total reports the group table's shape rather than the palette's.
    counted: set[frozenset[str]] = set()
    for title, tokens in GROUPS.items():
        present = [t for t in tokens if t in palette]
        print(f"\n--- {title} ---")
        print(f"{'pair':<34}" + "".join(f"{m:>9}" for m in VISION_MODES))
        for x, y in combinations(present, 2):
            row = []
            for mode in VISION_MODES:
                vx = palette[x] if mode == "normal" else simulate(palette[x], mode)
                vy = palette[y] if mode == "normal" else simulate(palette[y], mode)
                row.append(delta_e(oklab(vx), oklab(vy)))
            worst_cvd = min(row[1:])
            # Only the trichromatic separation is BINDING, and only for a pair with no declared
            # non-colour channel: the doctrine allows a pair to collapse under CVD provided shape,
            # line style or position carries the distinction. The report marks those pairs so the
            # redundancy can be checked in the render, and does not fail on them.
            mark = ""
            if (channel := EXEMPT.get(frozenset({x, y}))) is not None:
                mark = f"  -- {channel}"
            elif row[0] < DE_FLOOR:
                mark = "  << under 0.15"
                if frozenset({x, y}) not in counted:
                    counted.add(frozenset({x, y}))
                    failures += 1
            elif worst_cvd < DE_FLOOR:
                mark = "  << colour alone is not enough"
            print(f"{x + ' / ' + y:<34}" + "".join(f"{v:>9.3f}" for v in row) + mark)

    return failures


def emit_cvd(palette: dict[str, str], path: Path, scheme: str) -> None:
    """Write a LaTeX fragment defining every token as seen under each vision mode.

    The report gives numbers; this gives the proof sheet something to SHOW. A dE of 0.031 between
    two tokens under tritanopia is a fact one has to trust, while two swatches that are visibly the
    same colour is a fact one can act on -- and the poster's rule is that colour may not be the only
    channel, which is a judgement about a render, not about a number.

    Each token ``t`` is emitted as ``t@protan``, ``t@deutan``, ``t@tritan`` and ``t@grey``. The ``@``
    keeps the simulated names in a namespace of their own: they can never be reached by an ordinary
    call site, which would otherwise be one typo away from shipping a simulated colour on the poster.
    """
    lines = [
        f"% GENERATED by scripts/palette-check.py for scheme `{scheme}'. Do not edit.",
        "% Simulated colour-vision-deficiency renderings of every palette token, for the proof sheet.",
        "% Regenerate:  python scripts/palette-check.py <scheme> --emit-cvd generated/cvd-palette.tex",
        "",
    ]
    for token in sorted(palette):
        for mode in ("protan", "deutan", "tritan", "grey"):
            lines.append(
                f"\\definecolor{{{token}@{mode}}}{{HTML}}{{{simulate(palette[token], mode)}}}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {path} ({len(palette)} tokens x 4 modes)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scheme", nargs="?", default="base", help="scheme name under schemes/")
    parser.add_argument(
        "--grey-for",
        metavar="TOKEN",
        help="print the neutral grey matching that token's OKLab lightness, and exit",
    )
    parser.add_argument(
        "--emit-cvd",
        metavar="PATH",
        help="write simulated-vision colour definitions for the proof sheet, and exit",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    values = root / "parts" / "colors-values.tex"
    scheme_file = root / "schemes" / f"{args.scheme}.tex"

    if args.grey_for:
        palette = read_palette(values)
        token = args.grey_for
        if token not in palette:
            raise SystemExit(f"palette-check: unknown token: {token}")
        grey = grey_matching(palette[token])
        print(
            f"{token} = {palette[token]} (OKLab L {oklab(palette[token])[0]:.3f}) "
            f"-> matching grey {grey} (L {oklab(grey)[0]:.3f}, "
            f"contrast on ground {contrast(grey, palette['posterbg']):.2f}:1)"
        )
        return 0

    if args.emit_cvd:
        emit_cvd(read_palette(values, scheme_file), Path(args.emit_cvd), args.scheme)
        return 0

    palette = read_palette(values, scheme_file)
    failures = report(palette, args.scheme)
    print(f"\n{failures} binding failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
