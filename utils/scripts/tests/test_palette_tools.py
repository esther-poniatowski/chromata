"""Tests of the palette tools: colour science, palette reading, specification, report, proof, recolouring."""

from __future__ import annotations

import doctest
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

import check_palette
import recolour_assets
from palette_tools import colour, emit, latex_palette
from palette_tools.latex_palette import PaletteSourceError, parse_palette, read_palette
from palette_tools.proof import proof_sheet
from palette_tools.recolour import recolour_row, unmix
from palette_tools.report import report
from palette_tools.spec import AcceptanceTests, RecolourRow, SpecError, load_spec

SPEC = """
schema_version: 1
legacy_hue_names: toy palette of the tests
layers:
  toy:
    gloss: toy tokens
    tokens:
      bg: {value: FFFFFF, use: ground}
      dark: {value: "000000", use: dark mark, contrast: mark}
      pale: {value: EEEEEE, use: pale mark, contrast: mark}
      red: {value: FF0000, use: first, pole: warm, rung: deep}
      redish: {value: FE0101, use: second, pole: warm, rung: core}
      blue: {value: 0000FF, use: third}
      wash: {value: E6E6FF, use: wash, contrast: fill}
roles:
  accent: {of: blue, use: accent}
  tinted: {of: blue, tint: 10, use: tinted accent}
modes:
  dark:
    gloss: dark rendering
    values: {bg: "111111"}
css:
  bg: bg
  accent: accent
tests:
  ground: bg
  groups:
    pair: [red, redish, blue]
  exempt:
    - {pair: [red, blue], channel: line style}
recolour:
  targets: [red, blue]
  rows:
    - {name: row, strategy: unmix, files: [a.png, b.png, ab.png]}
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


def _spec(tmp_path: Path, text: str = SPEC, name: str = "palette.yml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_spec_reads_every_table(tmp_path: Path) -> None:
    spec = load_spec(_spec(tmp_path), tmp_path)
    assert spec.tests is not None and spec.tests.ground == "bg"
    assert spec.tests.exempt == {frozenset({"red", "blue"}): "line style"}
    assert spec.tests.marks == ("dark", "pale") and spec.tests.fills == ("wash",)
    assert spec.tests.ladder == {"red": ("warm", 0), "redish": ("warm", 1)}
    assert spec.recolour is not None and spec.recolour.rows[0].mixture == "ab.png"
    values = spec.values()
    assert values["accent"] == "0000FF" and values["tinted"] == colour.srgb_to_hex((0.9, 0.9, 1.0))
    assert spec.values("dark")["bg"] == "111111"


def test_an_extending_palette_names_the_tokens_of_its_base(tmp_path: Path) -> None:
    _spec(tmp_path)
    (tmp_path / "child").mkdir()
    child = _spec(tmp_path / "child", (
        "schema_version: 1\nextends: palette.yml\nlayers:\n  own:\n    gloss: own tokens\n"
        "    tokens:\n      extra: {value: \"123456\", use: extra}\n"
        "roles:\n  borrowed: {of: accent, use: a role of the base}\n"))
    values = load_spec(child, tmp_path).values()
    assert values["borrowed"] == "0000FF" and values["extra"] == "123456"


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: s.replace("  ground: bg\n", ""),                                   # no ground
        lambda s: s.replace("targets: [red, blue]", "targets: [red]"),               # one target
        lambda s: s.replace("strategy: unmix", "strategy: blur"),
        lambda s: s.replace("files: [a.png, b.png, ab.png]", "files: [a.png, b.png]"),
        lambda s: s.replace("contrast: mark}", "below_floor: framed}", 1),           # no contrast
        lambda s: s.replace("legacy_hue_names: toy palette of the tests\n", ""),     # hue names
        lambda s: s.replace("{of: blue, use: accent}", "{of: absent, use: accent}"),  # unknown token
        lambda s: s.replace("bg: {value: FFFFFF", "bg: {value: ffffff"),            # lowercase value
    ],
)
def test_load_spec_rejects_malformed_palettes(tmp_path: Path, edit) -> None:
    with pytest.raises(SpecError):
        load_spec(_spec(tmp_path, edit(SPEC)), tmp_path)


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


def test_report_honours_accepted_marks_and_flags_stale_acceptances() -> None:
    palette = parse_palette(PALETTE)
    accepted = AcceptanceTests(ground="bg", marks=("dark", "pale"), accepted={"pale": "framed"})
    text, failures = report(palette, accepted, "toy")
    assert failures == 0 and "-- accepted: framed" in text
    # An acceptance of a passing mark, or of a token that is not a mark, licenses nothing.
    stale = AcceptanceTests(ground="bg", marks=("dark",), accepted={"dark": "x", "wash": "y"})
    text, failures = report(palette, stale, "toy")
    assert failures == 2 and "drop the acceptance" in text and "is not a mark" in text


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


def test_report_fails_on_adjacent_rungs() -> None:
    palette = {"bg": "FFFFFF", "a": "000000", "b": "FFFF00"}
    tests = AcceptanceTests(ground="bg", groups={"g": ("a", "b")},
                            ladder={"a": ("p", 0), "b": ("p", 1)})
    text, failures = report(palette, tests, "toy")
    assert failures == 1 and "adjacent rungs of `p'" in text


def test_check_palette_exit_codes(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    assert check_palette.main(["--spec", str(spec)]) == 1      # red / redish adjacent and too close
    passing = _spec(tmp_path, SPEC.replace("    pair: [red, redish, blue]\n", "    pair: [dark, blue]\n")
                    .replace("use: pale mark, contrast: mark", "use: pale mark, contrast: mark, below_floor: framed"),
                    "passing.yml")
    assert check_palette.main(["--spec", str(passing)]) == 0
    assert check_palette.main(["--spec", str(passing), "--mode", "dark"]) == 1   # pale on a dark ground
    assert check_palette.main(["--spec", str(passing), "--mode", "sepia"]) == 2
    assert check_palette.main(["--spec", str(passing), "--palette", str(tmp_path / "absent.tex")]) == 2
    scheme = tmp_path / "scheme.tex"
    scheme.write_text("\\definecolor{pale}{HTML}{777777}\n", encoding="utf-8")
    assert check_palette.main(["--spec", str(passing), "--palette", str(scheme)]) == 1  # stale acceptance
    proof = tmp_path / "proof.tex"
    assert check_palette.main(["--spec", str(spec), "--emit-proof", str(proof)]) == 0
    assert proof.exists()


def test_recolour_assets_refuses_to_overwrite_its_sources(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    argv = ["--spec", str(spec), "--source", str(tmp_path), "--out", str(tmp_path)]
    assert recolour_assets.main(argv) == 2


def test_emitted_layers_and_css_block(tmp_path: Path) -> None:
    spec = load_spec(_spec(tmp_path), tmp_path)
    values = emit.latex_values(spec, "x/colors-values.tex")
    assert "\\definecolor{red}{HTML}{FF0000}" in values and "% deep -- first" in values
    assert parse_palette(values)["wash"] == "E6E6FF"
    roles = emit.latex_roles(spec, "x/colors-roles.tex")
    assert parse_palette(values + roles)["tinted"] == spec.values()["tinted"]
    block = emit.css_block(spec, "palette.yml", "  ")
    assert "  --accent: #0000FF;" in block and "@media (prefers-color-scheme: dark)" in block
    assert block.count("--bg:") == 2 and block.count("--accent:") == 1   # only changed names in dark
    assert block.startswith("  /* palette: palette.yml") and block.endswith("/* palette: end */")


def test_build_palette_writes_checks_and_scans(tmp_path: Path) -> None:
    import subprocess
    import build_palette
    folder = tmp_path / "artifacts" / "deck"
    folder.mkdir(parents=True)
    _spec(folder)
    page = folder / "index.html"
    page.write_text("<style>\n  /* palette: artifacts/deck/palette.yml */\n  /* palette: end */\n</style>\n",
                    encoding="utf-8")
    (folder / "slides.tex").write_text("\\input{colors-values}\n% \\definecolor{old}{HTML}{000000}\n",
                                       encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    root = ["--root", str(tmp_path)]
    assert build_palette.main([*root, "--check"]) == 1                 # outputs missing
    assert build_palette.main(root) == 0
    assert (folder / "colors-values.tex").exists() and (folder / "colors-roles.tex").exists()
    assert "--accent: #0000FF;" in page.read_text(encoding="utf-8")
    assert build_palette.main([*root, "--check"]) == 0
    (folder / "slides.tex").write_text("\\definecolor{local}{HTML}{000000}\n", encoding="utf-8")
    assert build_palette.main([*root, "--check"]) == 1                 # a colour outside a palette
