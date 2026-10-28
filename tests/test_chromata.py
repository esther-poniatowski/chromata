"""Tests of Chromata's colour science, specifications, projections and raster transforms."""

from __future__ import annotations

import doctest
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from chromata import build_cli, check_cli, colour, emit, latex_palette, recolour_cli
from chromata.latex_palette import PaletteSourceError, parse_palette, read_palette
from chromata.proof import proof_sheet
from chromata.recolour import recolour_row, unmix
from chromata.report import report
from chromata.spec import AcceptanceTests, LocalResolver, RecolourRow, SpecError, load_spec

TOY_HUES = """
schema_version: 1
level: hues
layers:
  toy:
    gloss: toy hues
    tokens:
      paper: {value: FFFFFF, use: white}
      ink: {value: "000000", use: black}
      mist: {value: EEEEEE, use: light grey}
      warmdeep: {value: FF0000, use: warm deep, pole: warm, rung: deep}
      warmcore: {value: FE0101, use: warm core, pole: warm, rung: core}
      cool: {value: 0000FF, use: cool}
      coolwash: {value: E6E6FF, use: cool wash}
"""

SPEC = """
schema_version: 1
level: concepts
extends: toyhues/palette.yml
roles:
  bg: {of: paper, use: ground}
  dark: {of: ink, use: dark mark, contrast: mark}
  pale: {of: mist, use: pale mark, contrast: mark}
  first: {of: warmdeep, use: first}
  second: {of: warmcore, use: second}
  third: {of: cool, use: third}
  wash: {of: coolwash, use: wash, contrast: fill}
  accent: {of: third, use: accent}
  tinted: {of: third, tint: 10, use: tinted accent}
modes:
  dark:
    gloss: dark rendering
    values: {bg: "111111", dark: "222222"}
    tests:
      ground: bg
css:
  bg: bg
  accent: accent
tests:
  ground: bg
  groups:
    pair: [first, second, third]
  exempt:
    - {pair: [first, third], channel: line style}
recolour:
  targets: [first, third]
  rows:
    - {name: row, strategy: unmix, files: [a.png, b.png, ab.png]}
"""

PALETTE = r"""
\definecolor{bg}{HTML}{FFFFFF}
\definecolor{dark}{HTML}{000000}
\definecolor{pale}{HTML}{EEEEEE}
\definecolor{first}{HTML}{FF0000}
\definecolor{second}{HTML}{FE0101}
\definecolor{third}{HTML}{0000FF}
\colorlet{wash}{third!10}
% \definecolor{retired}{HTML}{123456}
"""


@pytest.mark.parametrize("module", [colour, latex_palette])
def test_doctests(module: object) -> None:
    """The docstring examples hold."""
    assert doctest.testmod(module).failed == 0  # type: ignore[arg-type]


def test_package_source_has_no_vault_runtime_import() -> None:
    source_root = Path(__file__).parents[1] / "src" / "chromata"
    forbidden = ("from vault_paths", "import vault_paths", "from palette_tools", "import palette_tools")
    findings = [
        f"{path}:{token}"
        for path in source_root.rglob("*.py")
        for token in forbidden
        if token in path.read_text(encoding="utf-8")
    ]
    assert findings == []


def test_parse_palette_applies_overrides_tints_and_comments() -> None:
    base = parse_palette(PALETTE)
    assert base["wash"] == colour.srgb_to_hex((0.9, 0.9, 1.0))
    assert "retired" not in base
    over = parse_palette(r"\definecolor{first}{HTML}{00ff00}", base)
    assert over["first"] == "00FF00" and base["first"] == "FF0000"


def test_read_palette_reports_a_missing_source(tmp_path: Path) -> None:
    with pytest.raises(PaletteSourceError):
        read_palette(tmp_path / "absent.tex")


def test_simulate_rejects_an_unknown_mode() -> None:
    with pytest.raises(ValueError):
        colour.simulate("FF0000", "achromat")


def _spec(tmp_path: Path, text: str = SPEC, name: str = "palette.yml", root: Path | None = None) -> Path:
    hues = (root or tmp_path) / "toyhues"
    hues.mkdir(parents=True, exist_ok=True)
    (hues / "palette.yml").write_text(TOY_HUES, encoding="utf-8")
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_load_spec_reads_every_table(tmp_path: Path) -> None:
    spec = load_spec(_spec(tmp_path), tmp_path)
    assert spec.tests is not None and spec.tests.ground == "bg"
    assert spec.tests.exempt == {frozenset({"first", "third"}): "line style"}
    assert spec.tests.marks == ("dark", "pale") and spec.tests.fills == ("wash",)
    assert spec.tests.ladder["first"] == ("warm", 0) and spec.tests.ladder["second"] == ("warm", 1)
    assert spec.recolour is not None and spec.recolour.rows[0].mixture == "ab.png"
    values = spec.values()
    assert values["accent"] == "0000FF" and values["tinted"] == colour.srgb_to_hex((0.9, 0.9, 1.0))
    assert spec.values("dark")["bg"] == "111111"
    dark = spec.tests_for("dark")
    assert dark is not None and dark.marks == ("dark",) and dark.fills == ()   # overridden tokens only


def test_an_extending_palette_names_the_tokens_of_its_base(tmp_path: Path) -> None:
    _spec(tmp_path)
    (tmp_path / "child").mkdir()
    child = _spec(tmp_path / "child", (
        "schema_version: 1\nlevel: concepts\nextends: palette.yml\n"
        "roles:\n  borrowed: {of: accent, use: a role of the base}\n"), root=tmp_path)
    assert load_spec(child, tmp_path).values()["borrowed"] == "0000FF"


@pytest.mark.parametrize("name", ["hues.palette.yml", "style.palette.yml", "concepts.palette.yml"])
def test_shipped_examples_are_valid(name: str) -> None:
    examples = Path(__file__).parents[1] / "examples"
    assert load_spec(examples / name, examples).level in {"hues", "style", "concepts"}


@pytest.mark.parametrize("name", ["style.palette.yml", "concepts.palette.yml"])
def test_shipped_examples_pass_their_acceptance_checks(name: str) -> None:
    examples = Path(__file__).parents[1] / "examples"
    assert check_cli.main(["--root", str(examples), "--spec", str(examples / name)]) == 0


def test_an_extending_palette_accepts_a_descriptive_palette_filename(tmp_path: Path) -> None:
    base = tmp_path / "house-hues.palette.yml"
    base.write_text(TOY_HUES, encoding="utf-8")
    child = tmp_path / "house-style.palette.yml"
    child.write_text(
        "schema_version: 1\nlevel: concepts\nextends: house-hues.palette.yml\n"
        "roles:\n  borrowed: {of: cool, use: a role of the base}\n",
        encoding="utf-8",
    )
    assert load_spec(child).values()["borrowed"] == "0000FF"


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: s.replace("  ground: bg\n", ""),                                   # no ground
        lambda s: s.replace("targets: [first, third]", "targets: [first]"),               # one target
        lambda s: s.replace("strategy: unmix", "strategy: blur"),
        lambda s: s.replace("files: [a.png, b.png, ab.png]", "files: [a.png, b.png]"),
        lambda s: s.replace("contrast: mark}", "below_floor: framed}", 1),           # no contrast
        lambda s: s.replace("{of: third, use: accent}", "{of: absent, use: accent}"),  # unknown token
        lambda s: s.replace("level: concepts", "level: palettes"),                # unknown level
        lambda s: s.replace("level: concepts\n", ""),                               # no level
    ],
)
def test_load_spec_rejects_malformed_palettes(tmp_path: Path, edit) -> None:
    with pytest.raises(SpecError):
        load_spec(_spec(tmp_path, edit(SPEC)), tmp_path)


def test_report_counts_binding_failures_once_and_honours_exemptions() -> None:
    palette = parse_palette(PALETTE)
    tests = AcceptanceTests(
        ground="bg",
        groups={"one": ("first", "second", "third"), "two": ("first", "second")},
        exempt={frozenset({"first", "third"}): "line style"},
        marks=("dark", "pale"),
        fills=("wash",),
    )
    text, failures = report(palette, tests, "toy")
    # `pale' under the contrast floor, and first / second under the distance floor, counted once
    # although the pair sits in two groups; first / third is exempt.
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


def test_report_binds_marks_on_their_own_ground() -> None:
    palette = {"bg": "FFFFFF", "badge": "000000", "ink": "111111", "label": "FFFFFF"}
    tests = AcceptanceTests(ground="bg", pairs=(("ink", "badge"), ("label", "badge")))
    text, failures = report(palette, tests, "toy")
    assert failures == 1 and "ink on badge" in text and "label on badge" in text


def test_report_fails_on_adjacent_rungs() -> None:
    palette = {"bg": "FFFFFF", "a": "000000", "b": "FFFF00"}
    tests = AcceptanceTests(ground="bg", groups={"g": ("a", "b")},
                            ladder={"a": ("p", 0), "b": ("p", 1)})
    text, failures = report(palette, tests, "toy")
    assert failures == 1 and "adjacent rungs of `p'" in text


def test_check_palette_exit_codes(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    root = ["--root", str(tmp_path)]
    assert check_cli.main(["--spec", str(spec), *root]) == 1      # first / second adjacent and too close
    passing = _spec(tmp_path, SPEC.replace("    pair: [first, second, third]\n", "    pair: [dark, third]\n")
                    .replace("use: pale mark, contrast: mark", "use: pale mark, contrast: mark, below_floor: framed"),
                    "passing.yml")
    assert check_cli.main(["--spec", str(passing), *root]) == 0
    assert check_cli.main(["--spec", str(passing), "--mode", "dark", *root]) == 1   # dark on a dark ground
    accepted = _spec(tmp_path, passing.read_text(encoding="utf-8").replace(
        "    tests:\n      ground: bg\n",
        "    tests:\n      ground: bg\n      accepted:\n        - {token: dark, reason: framed}\n"),
        "accepted.yml")
    assert check_cli.main(["--spec", str(accepted), "--mode", "dark", *root]) == 0
    assert check_cli.main(["--spec", str(passing), "--mode", "sepia", *root]) == 2
    assert check_cli.main(["--spec", str(passing), "--palette", str(tmp_path / "absent.tex"), *root]) == 2
    scheme = tmp_path / "scheme.tex"
    scheme.write_text("\\definecolor{mist}{HTML}{777777}\n", encoding="utf-8")   # a scheme retunes a hue
    assert check_cli.main(["--spec", str(passing), "--palette", str(scheme), *root]) == 1  # stale acceptance
    proof = tmp_path / "proof.tex"
    assert check_cli.main(["--spec", str(spec), "--emit-proof", str(proof), *root]) == 0
    assert proof.exists()


def test_recolour_assets_refuses_to_overwrite_its_sources(tmp_path: Path) -> None:
    spec = _spec(tmp_path)
    argv = ["--spec", str(spec), "--source", str(tmp_path), "--out", str(tmp_path), "--root", str(tmp_path)]
    assert recolour_cli.main(argv) == 2


def test_emitted_layers_and_css_block(tmp_path: Path) -> None:
    spec = load_spec(_spec(tmp_path), tmp_path)
    values = emit.latex_values(spec.base, "x/colors-values.tex")
    assert values.startswith("% Generated from x/colors-values.tex by chromata-build.\n")
    assert "\\definecolor{warmdeep}{HTML}{FF0000}" in values and "% deep -- warm deep" in values
    assert parse_palette(values)["coolwash"] == "E6E6FF"
    roles = emit.latex_roles(spec, "x/colors-roles.tex")
    assert parse_palette(values + roles)["tinted"] == spec.values()["tinted"]
    block = emit.css_block(spec, "palette.yml", "  ")
    assert "  --accent: #0000FF;" in block and "@media (prefers-color-scheme: dark)" in block
    assert block.count("--bg:") == 2 and block.count("--accent:") == 1   # only changed names in dark
    assert block.startswith("  /* palette: palette.yml") and block.endswith("/* palette: end */")


def test_tex_prefixes_separate_value_and_role_namespaces(tmp_path: Path) -> None:
    spec = load_spec(_spec(tmp_path), tmp_path)
    values_projection = emit.TeXProjection.for_spec(spec.base, values_prefix="house-hue-")
    roles_projection = emit.TeXProjection.for_spec(
        spec,
        values_prefix="house-hue-",
        roles_prefix="house-",
        names={"first": "first-input"},
    )
    values = emit.latex_values(spec.base, "values.tex", values_projection)
    roles = emit.latex_roles(spec, "roles.tex", projection=roles_projection)
    assert "\\definecolor{house-hue-warmdeep}" in values
    assert "\\colorlet{house-first-input}{house-hue-warmdeep}" in roles
    assert "\\colorlet{house-accent}{house-third}" in roles


def test_build_command_writes_and_checks_explicit_targets(tmp_path: Path) -> None:
    folder = tmp_path / "deck"
    folder.mkdir(parents=True)
    spec = _spec(folder, root=tmp_path)
    css = folder / "palette.css"
    args = ["--root", str(tmp_path), "--spec", str(spec), "--css-out", str(css)]
    assert build_cli.main([*args, "--check"]) == 1
    assert build_cli.main(args) == 0
    assert (folder / "colors-roles.tex").exists() and not (folder / "colors-values.tex").exists()
    assert "--accent: #0000FF;" in css.read_text(encoding="utf-8")
    assert "/* palette: deck/palette.yml -- generated by chromata-build" in css.read_text(
        encoding="utf-8"
    )
    assert str(tmp_path) not in css.read_text(encoding="utf-8")
    roles = (folder / "colors-roles.tex").read_text(encoding="utf-8")
    assert roles.startswith("% Generated from deck/palette.yml by chromata-build.\n")
    assert str(tmp_path) not in roles
    assert build_cli.main([*args, "--check"]) == 0


@pytest.mark.parametrize("option", [
    ["--tex-name", "missing-separator"],
    ["--source-label", "bad*/comment"],
])
def test_build_command_rejects_an_unsafe_tex_name(option: list[str]) -> None:
    with pytest.raises(SystemExit):
        build_cli.build_parser().parse_args(
            ["--root", ".", "--spec", "palette.yml", *option]
        )


@pytest.mark.parametrize(
    "extra",
    [
        ["--roles-out", "$SPEC"],
        ["--roles-out", "same.tex", "--css-out", "same.tex"],
        ["--tex-name", "absent=public"],
        ["--tex-name", "first=one", "--tex-name", "first=two"],
        ["--tex-name", "first=shared", "--tex-name", "second=shared"],
        ["--tex-name", "first=bad\\name"],
        ["--roles-prefix", "bad{prefix}"],
    ],
)
def test_build_command_rejects_ambiguous_outputs(tmp_path: Path, extra: list[str]) -> None:
    spec = _spec(tmp_path)
    resolved = [str(spec) if value == "$SPEC" else value for value in extra]
    args = ["--root", str(tmp_path), "--spec", str(spec), *resolved]
    assert build_cli.main(args) == 2


@pytest.mark.parametrize(
    "settings",
    [
        {"roles_prefix": "bad{prefix}"},
        {"names": {"first": "bad\\name"}},
        {"names": {"absent": "public"}},
        {"names": {"first": "shared", "second": "shared"}},
        {"names": {"first": "black"}},
    ],
)
def test_projection_api_rejects_an_invalid_tex_interface(
    tmp_path: Path, settings: dict[str, object]
) -> None:
    spec = load_spec(_spec(tmp_path), tmp_path)
    with pytest.raises(emit.ProjectionError):
        emit.TeXProjection.for_spec(spec, **settings)


def test_projection_api_rejects_a_different_token_role_partition(tmp_path: Path) -> None:
    spec = load_spec(_spec(tmp_path), tmp_path)
    values_projection = emit.TeXProjection.for_spec(spec.base)
    with pytest.raises(emit.ProjectionError, match="partition"):
        emit.latex_roles(spec, "roles.tex", projection=values_projection)


def test_local_resolver_rejects_root_escape(tmp_path: Path) -> None:
    with pytest.raises(SpecError, match="escapes"):
        LocalResolver(tmp_path).resolve("../outside/palette.yml", source=tmp_path / "palette.yml")


def test_load_spec_rejects_extension_cycles(tmp_path: Path) -> None:
    first = tmp_path / "palette.yml"
    second_dir = tmp_path / "second"
    second_dir.mkdir()
    second = second_dir / "palette.yml"
    first.write_text("schema_version: 1\nlevel: concepts\nextends: second/palette.yml\n", encoding="utf-8")
    second.write_text("schema_version: 1\nlevel: concepts\nextends: palette.yml\n", encoding="utf-8")
    with pytest.raises(SpecError, match="cycle"):
        load_spec(first, tmp_path)


HUES = """
schema_version: 1
level: hues
layers:
  sama:
    gloss: toy hues
    tokens:
      paper: {value: FFFFFF, use: page}
      ink: {value: "000000", use: text}
      azuredeep: {value: 003A62, use: deep azure, pole: azure, rung: deep}
      azurecore: {value: 025F99, use: azure, pole: azure, rung: core}
"""

CONCEPTS = """
schema_version: 1
level: concepts
extends: hues/palette.yml
roles:
  ground: {of: paper, use: page ground}
  source: {of: azuredeep, use: the source, contrast: mark}
  transform: {of: azurecore, use: the transformation, contrast: mark}
  wash: {of: azurecore, tint: 10, use: pooling, contrast: fill}
modes:
  dark:
    gloss: dark rendering
    values: {ground: "111111"}
tests:
  ground: ground
  groups:
    poles: [source, transform]
"""


def _levels(tmp_path: Path) -> Path:
    (tmp_path / "hues").mkdir()
    _spec(tmp_path / "hues", HUES)
    (tmp_path / "concepts").mkdir()
    return _spec(tmp_path / "concepts", CONCEPTS)


def test_levels_bind_concepts_to_hues(tmp_path: Path) -> None:
    spec = load_spec(_levels(tmp_path), tmp_path)
    assert spec.values()["transform"] == "025F99"
    assert spec.values("dark")["ground"] == "111111" and spec.values("dark")["source"] == "003A62"
    assert spec.tests is not None and spec.tests.marks == ("source", "transform")
    assert spec.tests.fills == ("wash",)
    assert spec.tests.ladder["transform"] == ("azure", 1)            # reached through the role
    text, failures = report(spec.values(), spec.tests, "toy")
    assert "adjacent rungs of `azure'" in text and failures >= 1
    measured = check_cli.measured_palette(tmp_path / "concepts" / "palette.yml", [], "dark", tmp_path)
    assert measured["ground"] == "111111"                            # role override in the checker


@pytest.mark.parametrize(
    ("folder", "text"),
    [
        ("concepts", CONCEPTS + "layers:\n  own:\n    gloss: own\n    tokens:\n      x: {value: 123456, use: x}\n"),
        ("hues", HUES + "roles:\n  page: {of: paper, use: page}\n"),
        ("concepts", CONCEPTS.replace("  source:", "  sourceblue:").replace("[source,", "[sourceblue,")),
    ],
)
def test_levels_admit_only_their_content(tmp_path: Path, folder: str, text: str) -> None:
    _levels(tmp_path)
    path = _spec(tmp_path / folder, text.replace("value: 123456", 'value: "123456"'))
    with pytest.raises(SpecError):
        load_spec(path, tmp_path)
