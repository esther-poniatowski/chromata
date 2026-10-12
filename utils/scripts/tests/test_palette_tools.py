"""Tests of the palette tools: colour science, palette reading, specification, report, proof, recolouring."""

from __future__ import annotations

import doctest
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import check_palette
import recolour_assets
from palette_tools import colour, latex_palette
from palette_tools.latex_palette import PaletteSourceError, parse_palette, read_palette
from palette_tools.proof import proof_sheet
from palette_tools.recolour import recolour_row, unmix
from palette_tools.report import report
from palette_tools.spec import AcceptanceTests, RecolourRow, SpecError, load_spec

SPEC = """
[tests]
ground = "bg"
marks = ["dark", "pale"]
fills = ["wash"]

[tests.groups]
"pair" = ["red", "redish", "blue"]

[[tests.exempt]]
pair = ["red", "blue"]
channel = "line style"

[recolour]
targets = ["red", "blue"]

[[recolour.rows]]
name = "row"
strategy = "unmix"
files = ["a.png", "b.png", "ab.png"]
"""

PALETTE = r"""
\definecolor{bg}{HTML}{FFFFFF}
\definecolor{dark}{HTML}{000000}
\definecolor{pale}{HTML}{EEEEEE}
\definecolor{red}{HTML}{FF0000}
\definecolor{redish}{HTML}{FE0101}
\definecolor{blue}{HTML}{0000FF}
\colorlet{wash}{blue!10}
% \definecolor{retired}{HTML}{123456}
"""


@pytest.mark.parametrize("module", [colour, latex_palette])
def test_doctests(module: object) -> None:
    """The docstring examples hold."""
    assert doctest.testmod(module).failed == 0  # type: ignore[arg-type]


def test_parse_palette_applies_overrides_tints_and_comments() -> None:
    base = parse_palette(PALETTE)
    assert base["wash"] == colour.srgb_to_hex((0.9, 0.9, 1.0))
    assert "retired" not in base
    over = parse_palette(r"\definecolor{red}{HTML}{00ff00}", base)
    assert over["red"] == "00FF00" and base["red"] == "FF0000"


def test_read_palette_reports_a_missing_source(tmp_path: Path) -> None:
    with pytest.raises(PaletteSourceError):
        read_palette(tmp_path / "absent.tex")


def test_simulate_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValueError):
        colour.simulate("FF0000", "achromat")


def test_load_spec_reads_both_tables(tmp_path: Path) -> None:
    path = tmp_path / "palette.toml"
    path.write_text(SPEC, encoding="utf-8")
    spec = load_spec(path)
    assert spec.tests is not None and spec.tests.ground == "bg"
    assert spec.tests.exempt == {frozenset({"red", "blue"}): "line style"}
    assert spec.recolour is not None and spec.recolour.rows[0].mixture == "ab.png"


@pytest.mark.parametrize(
    "text",
    [
        "[tests]\nmarks = ['a']\n",                                   # no ground
        "[recolour]\ntargets = ['a']\n",                              # one target
        "[recolour]\ntargets = ['a','b']\n[[recolour.rows]]\nstrategy='blur'\nfiles=['1','2','3']\n",
        "[recolour]\ntargets = ['a','b']\n[[recolour.rows]]\nstrategy='unmix'\nfiles=['1','2']\n",
    ],
)
def test_load_spec_rejects_malformed_tables(tmp_path: Path, text: str) -> None:
    path = tmp_path / "palette.toml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SpecError):
        load_spec(path)


def test_report_counts_binding_failures_once_and_honours_exemptions() -> None:
    palette = parse_palette(PALETTE)
    tests = AcceptanceTests(
        ground="bg",
        groups={"one": ("red", "redish", "blue"), "two": ("red", "redish")},
        exempt={frozenset({"red", "blue"}): "line style"},
        marks=("dark", "pale"),
        fills=("wash",),
    )
    text, failures = report(palette, tests, "toy")
    # `pale' under the contrast floor, and red / redish under the distance floor, counted once
    # although the pair sits in two groups; red / blue is exempt.
    assert failures == 2
    assert "-- line style" in text and "<< under 3:1" in text


def test_report_fails_without_a_ground() -> None:
    text, failures = report({"a": "000000"}, AcceptanceTests(ground="bg"), "toy")
    assert failures == 1 and "undefined" in text


def test_proof_sheet_defines_every_token_under_every_mode() -> None:
    palette = parse_palette(PALETTE)
    sheet = proof_sheet(palette, "toy")
    for token in palette:
        for mode in ("protan", "deutan", "tritan", "grey"):
            assert f"\\definecolor{{{token}@{mode}}}" in sheet
    assert sheet.rstrip().endswith("\\end{document}")


def _picture(path: Path, rgb: tuple[float, float, float]) -> None:
    pixels = np.zeros((4, 4, 4), dtype=np.uint8)
    pixels[..., :3] = np.array(rgb) * 255
    pixels[..., 3] = 255
    Image.fromarray(pixels, mode="RGBA").save(path)


def test_unmix_recovers_the_two_envelopes() -> None:
    s1, s2 = np.array([1.0, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])
    e1, e2 = unmix(np.array([[[0.3, 0.6, 0.0]]]), s1, s2)
    assert np.allclose(e1, 0.3) and np.allclose(e2, 0.6)


def test_recolour_row_repaints_a_mixture_into_the_targets(tmp_path: Path) -> None:
    src, out = tmp_path / "src", tmp_path / "out"
    src.mkdir()
    _picture(src / "a.png", (1.0, 0.0, 0.0))
    _picture(src / "b.png", (0.0, 1.0, 0.0))
    _picture(src / "ab.png", (0.5, 0.5, 0.0))
    targets = (np.array([0.0, 0.0, 1.0]), np.array([1.0, 1.0, 0.0]))
    recolour_row(RecolourRow("row", "unmix", "a.png", "b.png", "ab.png"), src, out, targets)
    mixed = np.asarray(Image.open(out / "ab.png"))[0, 0, :3] / 255.0
    assert np.allclose(mixed, [0.5, 0.5, 0.5], atol=0.01)


def test_check_palette_exit_codes(tmp_path: Path) -> None:
    values = tmp_path / "values.tex"
    values.write_text(PALETTE, encoding="utf-8")
    spec = tmp_path / "palette.toml"
    spec.write_text(SPEC, encoding="utf-8")
    assert check_palette.main(["--palette", str(values), "--spec", str(spec)]) == 1
    assert check_palette.main(["--palette", str(tmp_path / "absent.tex")]) == 2
    proof = tmp_path / "proof.tex"
    assert check_palette.main(["--palette", str(values), "--emit-proof", str(proof)]) == 0
    assert proof.exists()


def test_recolour_assets_refuses_to_overwrite_its_sources(tmp_path: Path) -> None:
    values = tmp_path / "values.tex"
    values.write_text(PALETTE, encoding="utf-8")
    spec = tmp_path / "palette.toml"
    spec.write_text(SPEC, encoding="utf-8")
    argv = ["--palette", str(values), "--spec", str(spec), "--source", str(tmp_path), "--out", str(tmp_path)]
    assert recolour_assets.main(argv) == 2
