#!/usr/bin/env python3
"""Re-paint the starting-point card's modality pictures into a scheme's component colours.

**The problem this exists for.** Every colour on the poster follows the selected scheme except the
three modality rows, because those are raster assets: ``assets/gratings-*.png``, ``soundwave-*.png``
and ``odor-*.png`` are painted in the BASE palette's red and green. A scheme that re-hues ``comp1``
and ``comp2`` therefore leaves that one card behind, and the contradiction lands on the same band as
the observation card's archetype legend, which does follow the palette. Nothing in the build reports
it; only the render shows it.

**Why a script and not a one-off edit in an image editor.** Two reasons, and the second is the
binding one:

1. The component colours are read out of the LaTeX sources with the same reader
   ``palette-check.py`` uses, so a recoloured asset cannot drift from the token it depicts. Retune
   ``comp1`` in a scheme, re-run this, and the pictures follow.
2. A hand-painted asset is an unexplained binary. Six months later nothing states which colours it
   was painted in, from what, or how to redo it after a palette change.

**Two strategies, each matched to how the artwork was actually made.** Neither is a hue rotation of
the whole image, which is what a naive recolour does and what gets the mixture panels wrong.

*Unmixing* (gratings, soundwaves). Each of these images is built from exactly two source colours:
one grating in red plus one in yellow-green, added; one waveform in red drawn over one in green.
Writing a pixel as ``env1 * S1 + env2 * S2`` and solving the (over-determined, 3x2) least-squares
system recovers the two envelopes exactly, and the picture is then re-composited as
``env1 * C1 + env2 * C2``. The mixture panel comes out right for free -- where the two gratings
superpose, the new picture superposes the new colours, which is what a superposition of two stimuli
is supposed to look like. Classifying pixels by hue instead would paint the crossings a flat average
and lose the summation the panel is about.

*Hue rotation* (odor plumes). These are semi-transparent smoke with a pronounced gradient along
their length -- magenta into orange, teal into emerald. Unmixing against two fixed colours would
flatten that gradient into one tint. Each cluster is instead rotated bodily onto its target hue and
its saturation scaled, which moves the gradient without straightening it.

**Both source colours are MEASURED, never assumed.** Each single-colour picture reports its own
brightest colour, and that measurement is what the mixture panel is unmixed against. The green
grating is a yellow-green, not a green; assuming a pure channel decomposition would have leaked a
third of its brightness into the red envelope, and the result would merely have looked a bit wrong.

Usage, from the poster directory (never from the base conda environment)::

    conda run -n geonexus python scripts/recolour-modality-assets.py petrol-guide

Outputs land in ``assets/<scheme>/`` under the SAME nine filenames the base assets carry, which is
what lets a scheme select them with one directory prefix (``\\gModalDir`` in
``parts/block-starting.tex``). The base assets are never touched.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location("pc", ROOT / "scripts" / "palette-check.py")
_pc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pc)

#: Each row of the starting-point card: the two single-component pictures and their mixture, with
#: the strategy that matches how the artwork was made. The mixture is listed last because the two
#: source colours are measured from the singles and then applied to it.
ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    ("vision", "unmix", "gratings-red.png", "gratings-green.png", "gratings-mixture-plaid.png"),
    ("audition", "unmix", "soundwave-red.png", "soundwave-green.png", "soundwave-mix.png"),
    ("olfaction", "rotate", "odor-fume-pink.png", "odor-fume-green.png", "odor-mix.png"),
)

#: A pixel takes part in a measurement only if it is opaque enough, coloured enough and bright
#: enough to state a hue. Anti-aliased rims and near-transparent smoke state nothing.
ALPHA_FLOOR = 0.35
SAT_FLOOR = 0.20
VAL_FLOOR = 0.12

#: How much of a plume's internal hue span survives the rotation (see :func:`recolour_rotate`).
#: Below about 0.3 the gradient flattens into one tint and the smoke loses its depth; above about
#: 0.6 an end of the span leaves its colour family.
SPAN_COMPRESSION = 0.42


def load(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Return an image as (RGB in [0,1], alpha in [0,1])."""
    a = np.asarray(Image.open(path).convert("RGBA")).astype(np.float64) / 255.0
    return a[..., :3], a[..., 3]


def save(path: Path, rgb: np.ndarray, alpha: np.ndarray) -> None:
    """Write RGB + alpha back to a PNG."""
    out = np.concatenate([np.clip(rgb, 0, 1), alpha[..., None]], axis=-1)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray((out * 255 + 0.5).astype(np.uint8), mode="RGBA").save(path)


def hsv(rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Hue in degrees, saturation and value, computed without a Python-level loop."""
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
    """Mask of pixels entitled to contribute to a measurement."""
    _, s, v = hsv(rgb)
    return (alpha > ALPHA_FLOOR) & (s > SAT_FLOOR) & (v > VAL_FLOOR)


def source_colour(path: Path) -> np.ndarray:
    """The picture's own brightest saturated colour -- what it is actually painted in.

    Taken as the mean of the top decile by value rather than the single brightest pixel, which on a
    compressed source is as likely to be an artefact as a sample.
    """
    rgb, alpha = load(path)
    m = usable(rgb, alpha)
    if not m.any():
        raise SystemExit(f"recolour: {path.name} states no colour to measure")
    v = rgb.max(-1)[m]
    cut = np.quantile(v, 0.90)
    sel = rgb[m][v >= cut]
    return sel.mean(axis=0)


def circular_mean(deg: np.ndarray) -> float:
    """Mean of an angle sample, taken on the circle so a cluster straddling 0 does not average to 180."""
    a = np.radians(deg)
    return float(np.degrees(np.arctan2(np.sin(a).mean(), np.cos(a).mean())) % 360)


def unmix(rgb: np.ndarray, s1: np.ndarray, s2: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split a picture into the two envelopes that compose it, given its two source colours.

    Least squares on ``rgb = env1 * s1 + env2 * s2`` per pixel: three equations, two unknowns, so a
    pixel that is neither colour (a compression artefact, a stray blue) resolves to the closest
    combination rather than to nonsense. Negative envelopes are clipped away -- an envelope is an
    amount of light and cannot be negative.
    """
    basis = np.stack([s1, s2], axis=1)                     # 3 x 2
    pinv = np.linalg.pinv(basis)                           # 2 x 3
    env = np.einsum("kc,...c->...k", pinv, rgb)
    return np.clip(env[..., 0], 0, None), np.clip(env[..., 1], 0, None)


def recolour_unmix(path: Path, out: Path, s1: np.ndarray, s2: np.ndarray,
                   c1: np.ndarray, c2: np.ndarray) -> str:
    rgb, alpha = load(path)
    e1, e2 = unmix(rgb, s1, s2)
    save(out, e1[..., None] * c1 + e2[..., None] * c2, alpha)
    return f"unmix  env1 mean {e1.mean():.3f}  env2 mean {e2.mean():.3f}"


def recolour_rotate(path: Path, out: Path, anchors: tuple[float, float],
                    targets: tuple[np.ndarray, np.ndarray]) -> str:
    """Rotate each hue cluster onto its target, preserving the gradient inside the cluster.

    Two things this deliberately does NOT do, both learned from getting them wrong:

    * **It does not touch saturation.** Scaling each pixel's saturation toward the target's turns
      pale smoke into a vivid ribbon: the plumes sit around a quarter of the target's saturation, so
      the scale factor is three to five, and the result is a different picture rather than the same
      picture in another colour. The plume's paleness is its character.
    * **It rotates every pixel that has a hue at all**, not only the saturated ones. Restricting the
      rotation to pixels above a saturation floor leaves the pale head of each plume behind at its
      original hue, so a plume ends green at the top and blue at the bottom -- which reads as two
      substances rather than one.
    """
    rgb, alpha = load(path)
    h, s, v = hsv(rgb)
    th = [hsv(t.reshape(1, 1, 3))[0][0, 0] for t in targets]
    # Which cluster each pixel belongs to: the nearer anchor on the hue circle.
    d0 = (h - anchors[0] + 180) % 360 - 180
    d1 = (h - anchors[1] + 180) % 360 - 180
    pick1 = np.abs(d1) < np.abs(d0)
    # THE SPAN IS COMPRESSED, NOT ONLY SHIFTED. Each plume runs across some 60 deg of hue -- magenta
    # into orange, teal into emerald -- and a rigid rotation carries the whole span onto the target,
    # so one end lands outside the family: vermilion's plume ends gold and slate blue's ends violet,
    # and the violet collides with the mixture's own colour. Shrinking the span about the anchor
    # keeps the gradient's direction and its shape while holding both ends inside one family.
    span = np.where(pick1, d1, d0) * SPAN_COMPRESSION
    anchor = np.where(pick1, th[1], th[0])
    # A true grey states no hue, so rotating it would invent one.
    keep = (alpha > 0.004) & (s > 0.02)
    h2 = np.where(keep, (anchor + span) % 360, h)
    save(out, from_hsv(h2, s, v), alpha)
    return (f"rotate {keep.mean():.2f} of pixels, "
            f"{pick1[keep].mean():.2f} of them toward the second anchor")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scheme", help="scheme name under schemes/, e.g. petrol-guide")
    args = parser.parse_args()

    scheme_file = ROOT / "schemes" / f"{args.scheme}.tex"
    if not scheme_file.exists():
        raise SystemExit(f"recolour: no such scheme: {scheme_file}")
    palette = _pc.read_palette(ROOT / "parts" / "colors-values.tex", scheme_file)
    c1 = np.array(_pc.hex_to_srgb(palette["comp1"]))
    c2 = np.array(_pc.hex_to_srgb(palette["comp2"]))
    print(f"=== scheme {args.scheme}: comp1 #{palette['comp1']}, comp2 #{palette['comp2']} ===")

    dest = ROOT / "assets" / args.scheme
    for row, strategy, f1, f2, fmix in ROWS:
        src = ROOT / "assets"
        s1, s2 = source_colour(src / f1), source_colour(src / f2)
        print(f"\n{row} ({strategy}): measured sources "
              f"#{_pc.srgb_to_hex(tuple(s1))} and #{_pc.srgb_to_hex(tuple(s2))}")
        for name in (f1, f2, fmix):
            if strategy == "unmix":
                note = recolour_unmix(src / name, dest / name, s1, s2, c1, c2)
            else:
                anchors = []
                for sf in (f1, f2):
                    rgb, alpha = load(src / sf)
                    m = usable(rgb, alpha)
                    hh, _, _ = hsv(rgb)
                    anchors.append(circular_mean(hh[m]))
                note = recolour_rotate(src / name, dest / name, (anchors[0], anchors[1]), (c1, c2))
            print(f"  {name:<32}{note}")
    print(f"\nwrote {sum(3 for _ in ROWS)} pictures to {dest.relative_to(ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
