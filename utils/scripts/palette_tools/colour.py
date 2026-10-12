"""
Colour science used by the palette tools, dependency-free.

* OKLab (Ottosson 2020) for perceptual distance.
* WCAG 2.1 relative luminance for contrast.
* Machado, Oliveira & Fernandes (2009) severity-1.0 matrices for the three dichromacies, applied in
  linear RGB.

Every colour crosses the public functions as an uppercase ``RRGGBB`` string, so that values read
from LaTeX sources and values written back to them share one representation.
"""

from __future__ import annotations

import math

RGB = tuple[float, float, float]
Lab = tuple[float, float, float]

#: Vision modes in report order; ``normal`` is the trichromat reference.
VISION_MODES: tuple[str, ...] = ("normal", "protan", "deutan", "tritan", "grey")

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


def hex_to_srgb(value: str) -> RGB:
    """
    Convert ``RRGGBB`` to sRGB channels in [0, 1].

    Parameters
    ----------
    value : str
        Six hexadecimal digits, with or without a leading ``#``.

    Returns
    -------
    RGB
        The three channels.

    Examples
    --------
    >>> hex_to_srgb("FFFFFF")
    (1.0, 1.0, 1.0)
    """
    v = value.lstrip("#")
    return (int(v[0:2], 16) / 255.0, int(v[2:4], 16) / 255.0, int(v[4:6], 16) / 255.0)


def srgb_to_hex(rgb: RGB) -> str:
    """
    Convert sRGB channels in [0, 1] to an uppercase ``RRGGBB`` string, clipping out-of-gamut values.

    Examples
    --------
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
    """Apply the sRGB transfer function, clipping to [0, 1] first."""

    def f(c: float) -> float:
        c = min(1.0, max(0.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055

    return (f(rgb[0]), f(rgb[1]), f(rgb[2]))


def linear_to_oklab(rgb: RGB) -> Lab:
    """Convert linear RGB to OKLab (Ottosson 2020)."""
    r, g, b = rgb
    # Cone-like responses (long, medium, short), then their cube roots.
    long_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    medium = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    short = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (long_, medium, short))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab(hex_value: str) -> Lab:
    """
    OKLab coordinates of an ``RRGGBB`` colour.

    Examples
    --------
    >>> round(oklab("FFFFFF")[0], 3)
    1.0
    """
    return linear_to_oklab(to_linear(hex_to_srgb(hex_value)))


def delta_e(a: Lab, b: Lab) -> float:
    """Euclidean OKLab distance between two colours."""
    return math.dist(a, b)


def luminance(hex_value: str) -> float:
    """WCAG relative luminance of an ``RRGGBB`` colour."""
    r, g, b = to_linear(hex_to_srgb(hex_value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """
    WCAG contrast ratio between two ``RRGGBB`` colours.

    Examples
    --------
    >>> round(contrast("FFFFFF", "000000"), 1)
    21.0
    """
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def grey_matching(hex_value: str) -> str:
    """
    The neutral grey with the same OKLab lightness as ``hex_value``.

    For a neutral the three OKLab cone responses are equal and the matrix rows sum to one, so
    ``L = v**(1/3)`` in linear RGB and the inversion is exact.

    Examples
    --------
    >>> grey_matching("FFFFFF")
    'FFFFFF'
    """
    lightness = oklab(hex_value)[0]
    v = lightness**3
    return srgb_to_hex(from_linear((v, v, v)))


def simulate(hex_value: str, mode: str) -> str:
    """
    Simulate a colour as seen under a vision mode.

    Parameters
    ----------
    hex_value : str
        The colour, as ``RRGGBB``.
    mode : str
        One of ``normal``, ``protan``, ``deutan``, ``tritan`` or ``grey``.

    Returns
    -------
    str
        The simulated colour, as ``RRGGBB``.

    Raises
    ------
    ValueError
        If ``mode`` is not a known vision mode.

    Examples
    --------
    >>> simulate("FFFFFF", "grey")
    'FFFFFF'
    """
    if mode == "normal":
        return hex_value.upper()
    lin = to_linear(hex_to_srgb(hex_value))
    if mode == "grey":
        y = 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]
        out: RGB = (y, y, y)
    elif mode in CVD_MATRICES:
        m = CVD_MATRICES[mode]
        out = (
            sum(m[0][j] * lin[j] for j in range(3)),
            sum(m[1][j] * lin[j] for j in range(3)),
            sum(m[2][j] * lin[j] for j in range(3)),
        )
    else:
        raise ValueError(f"unknown vision mode: {mode!r} (expected one of {VISION_MODES})")
    return srgb_to_hex(from_linear(out))
