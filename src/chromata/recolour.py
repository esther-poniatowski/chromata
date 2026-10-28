"""
Repainting two-colour raster pictures into two palette tokens.

A picture drawn in two colours keeps its meaning only if those colours follow the palette; a
raster asset does not, so a palette change leaves it behind. Two strategies are matched to how the
artwork was made, and neither is a hue rotation of the whole image, which gets mixtures wrong.

*Unmixing* suits pictures built from exactly two source colours, added or overlaid. Writing a pixel
as ``env1 * S1 + env2 * S2`` and solving the over-determined (3 x 2) least-squares system recovers
the two envelopes, and the picture is re-composited as ``env1 * C1 + env2 * C2``. Where the two
sources superpose, the result superposes the two targets.

*Hue rotation* suits semi-transparent pictures with a gradient along their length. Each hue cluster
is rotated onto its target hue, and its hue span is compressed about the anchor, which moves the
gradient without flattening it or letting an end leave the target's colour family.

Both source colours are measured from the single-colour pictures, never assumed.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

from chromata.spec import RecolourRow

#: A pixel takes part in a measurement only if it is opaque enough, coloured enough and bright
#: enough to state a hue. Anti-aliased rims and near-transparent smoke state nothing.
ALPHA_FLOOR = 0.35
SAT_FLOOR = 0.20
VAL_FLOOR = 0.12

#: Share of a plume's internal hue span kept by the rotation. Below about 0.3 the gradient flattens
#: into one tint; above about 0.6 an end of the span leaves its colour family.
SPAN_COMPRESSION = 0.42


class RecolourError(ValueError):
    """Raised when a picture states no colour to measure."""


def load(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return an image as (RGB in [0, 1], alpha in [0, 1])."""
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float64) / 255.0
    return a[..., :3], a[..., 3]


def save(path: Path, rgb: np.ndarray, alpha: np.ndarray) -> None:
    """Write RGB and alpha to a PNG, creating the parent folder."""
    out = np.concatenate([np.clip(rgb, 0, 1), alpha[..., None]], axis=-1)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8), mode="RGBA").save(path)


def hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hue in degrees, saturation and value, vectorised."""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = np.maximum(mx - mn, 1e-9)
    h = np.zeros_like(r)
    i = mx == r
    h[i] = (((g - b) / d) % 6)[i]
    i = (mx == g) & (mx != r)
    h[i] = (((b - r) / d) + 2)[i]
    i = (mx == b) & (mx != r) & (mx != g)
    h[i] = (((r - g) / d) + 4)[i]
    return (h * 60) % 360, np.where(mx > 0, (mx - mn) / np.maximum(mx, 1e-9), 0.0), mx


def from_hsv(h: np.ndarray, s: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Inverse of :func:`hsv`."""
    c = v * s
    hp = (h % 360) / 60.0
    x = c * (1 - np.abs(hp % 2 - 1))
    z = np.zeros_like(c)
    seq = [(c, x, z), (x, c, z), (z, c, x), (z, x, c), (x, z, c), (c, z, x)]
    out = np.zeros(h.shape + (3,))
    for k, (rr, gg, bb) in enumerate(seq):
        m = (hp >= k) & (hp < k + 1)
        for ci, ch in enumerate((rr, gg, bb)):
            out[..., ci][m] = ch[m]
    return out + (v - c)[..., None]


def usable(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Mask of the pixels entitled to contribute to a measurement."""
    _, s, v = hsv(rgb)
    return (alpha > ALPHA_FLOOR) & (s > SAT_FLOOR) & (v > VAL_FLOOR)


def source_colour(path: Path) -> np.ndarray:
    """
    The colour a single-colour picture is painted in.

    Taken as the mean of the top decile by value rather than the single brightest pixel, which on a
    compressed source is as likely to be an artefact as a sample.

    Raises
    ------
    RecolourError
        If no pixel of the picture is usable.
    """
    rgb, alpha = load(path)
    m = usable(rgb, alpha)
    if not m.any():
        raise RecolourError(f"{path.name} states no colour to measure")
    v = rgb.max(-1)[m]
    cut = np.quantile(v, 0.90)
    return rgb[m][v >= cut].mean(axis=0)


def circular_mean(deg: np.ndarray) -> float:
    """Mean of an angle sample on the circle, so a cluster straddling 0 does not average to 180."""
    a = np.radians(deg)
    return float(np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean())) % 360)


def unmix(rgb: np.ndarray, s1: np.ndarray, s2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """
    Split a picture into the two envelopes that compose it, given its two source colours.

    Negative envelopes are clipped: an envelope is an amount of light.
    """
    pinv = np.linalg.pinv(np.stack([s1, s2], axis=1))
    env = np.einsum("kc,...c->...k", pinv, rgb)
    return np.clip(env[..., 0], 0, None), np.clip(env[..., 1], 0, None)


def recolour_unmix(src: Path, out: Path, sources: tuple[np.ndarray, np.ndarray],
                   targets: tuple[np.ndarray, np.ndarray]) -> str:
    """Repaint one picture by unmixing it against its two source colours."""
    rgb, alpha = load(src)
    e1, e2 = unmix(rgb, *sources)
    save(out, e1[..., None] * targets[0] + e2[..., None] * targets[1], alpha)
    return f"unmix  env1 mean {e1.mean():.3f}  env2 mean {e2.mean():.3f}"


def recolour_rotate(src: Path, out: Path, anchors: tuple[float, float],
                    targets: tuple[np.ndarray, np.ndarray]) -> str:
    """
    Rotate each hue cluster of one picture onto its target, compressing its span.

    Saturation is left untouched, since pale smoke turned vivid is a different picture. Every pixel
    with a hue is rotated, since leaving the pale ones behind splits one plume into two colours.
    """
    rgb, alpha = load(src)
    h, s, v = hsv(rgb)
    th = [hsv(t.reshape(1, 1, 3))[0][0, 0] for t in targets]
    d0 = (h - anchors[0] + 180) % 360 - 180
    d1 = (h - anchors[1] + 180) % 360 - 180
    pick1 = np.abs(d1) < np.abs(d0)
    span = np.where(pick1, d1, d0) * SPAN_COMPRESSION
    anchor = np.where(pick1, th[1], th[0])
    keep = (alpha > 0.004) & (s > 0.02)
    h2 = np.where(keep, (anchor + span) % 360, h)
    save(out, from_hsv(h2, s, v), alpha)
    return (f"rotate {keep.mean():.2f} of pixels, "
            f"{pick1[keep].mean():.2f} of them toward the second anchor")


def recolour_row(row: RecolourRow, source_dir: Path, out_dir: Path,
                 targets: tuple[np.ndarray, np.ndarray]) -> list[str]:
    """
    Repaint the three pictures of one row.

    Parameters
    ----------
    row : RecolourRow
        Two single-colour pictures and their mixture.
    source_dir, out_dir : Path
        Where the pictures are read and written, under the same filenames.
    targets : tuple[np.ndarray, np.ndarray]
        The two target colours, as sRGB arrays in [0, 1].

    Returns
    -------
    list[str]
        One report line per picture, preceded by the measured source colours.
    """
    singles = (source_dir / row.first, source_dir / row.second)
    sources = (source_colour(singles[0]), source_colour(singles[1]))
    lines = [(f"{row.name} ({row.strategy}): measured sources "
              f"{tuple(round(float(c), 3) for c in sources[0])} and "
              f"{tuple(round(float(c), 3) for c in sources[1])}")]
    anchors: tuple[float, float] | None = None
    if row.strategy == "rotate":
        measured = []
        for single in singles:
            rgb, alpha = load(single)
            hh, _, _ = hsv(rgb)
            measured.append(circular_mean(hh[usable(rgb, alpha)]))
        anchors = (measured[0], measured[1])
    for name in (row.first, row.second, row.mixture):
        if anchors is None:
            note = recolour_unmix(source_dir / name, out_dir / name, sources, targets)
        else:
            note = recolour_rotate(source_dir / name, out_dir / name, anchors, targets)
        lines.append(f"  {name:<32}{note}")
    return lines
