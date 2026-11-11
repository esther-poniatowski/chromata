"""In-place refresh of marked page blocks, and build runs over every palette of a manifest."""

from __future__ import annotations

import doctest
from pathlib import Path

import pytest

from chromata import build_cli, page
from chromata.page import PageError, label_problem, marked_blocks, refresh_page
from chromata.schemas import MANIFEST_SCHEMA, PALETTE_SCHEMA, schema_violations

HUES = """
_schema: chromata:palette@1
level: hues
layers:
  base:
    gloss: toy hues
    tokens:
      paper: {value: FFFFFF, use: page}
      ink: {value: "000000", use: text}
      azure: {value: 025F99, use: azure}
"""

STYLE = """
_schema: chromata:palette@1
level: style
extends: hues/palette.yml
roles:
  pagebg: {of: paper, use: page ground}
  bodytext: {of: ink, use: body text}
modes:
  dark:
    gloss: dark rendering
    values: {pagebg: "111111"}
css:
  bg: pagebg
  text: bodytext
"""

CONCEPTS = """
_schema: chromata:palette@1
level: concepts
extends: hues/palette.yml
roles:
  signal: {of: azure, use: the signal}
css:
  signal: signal
"""

PAGE = (
    "<html>\r\n"
    "<style>\r\n"
    "    /* palette: style/palette.yml -- note kept by the consumer */\r\n"
    "    stale line\r\n"
    "    /* palette: end */\r\n"
    "  body { margin: 0 }\r\n"
    "</style>\r\n"
    "</html>"
)


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    return path


def _read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _consumer(root: Path) -> None:
    """Write a hue library, a style palette, a concept palette and one marked page."""
    _write(root / "hues" / "palette.yml", HUES)
    _write(root / "style" / "palette.yml", STYLE)
    _write(root / "concepts" / "palette.yml", CONCEPTS)
    _write(root / "site" / "index.html", PAGE)


MANIFEST = """
_schema: chromata:build-manifest@1
palettes:
  - spec: hues/palette.yml
  - spec: style/palette.yml
    css_pages: [site/index.html]
  - spec: concepts/palette.yml
    roles_output: concepts/roles.tex
"""


def test_page_doctests() -> None:
    assert doctest.testmod(page).failed == 0


def test_refresh_changes_only_the_lines_between_the_markers() -> None:
    refreshed = refresh_page(PAGE, {"style/palette.yml": [":root {", "  --bg: #FFFFFF;", "}"]})
    assert refreshed == PAGE.replace(
        "    stale line\r\n",
        "    :root {\r\n      --bg: #FFFFFF;\r\n    }\r\n",
    )
    assert refresh_page(refreshed, {"style/palette.yml": [":root {", "  --bg: #FFFFFF;", "}"]}) \
        == refreshed


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("/* palette: a.yml */\nbody\n", "has no closing marker"),
        ("/* palette: a.yml */\n/* palette: end */\n/* palette: end */\n",
         "closing marker without an opening marker"),
        ("/* palette: a.yml */\n/* palette: b.yml */\n/* palette: end */\n",
         "inside the block of `a.yml'"),
        (("/* palette: a.yml */\n/* palette: end */\n/* palette: a.yml -- again */\n"
          "/* palette: end */\n"), "marked more than once, on lines 1, 3"),
        ("/* palette: b.yml */\n/* palette: end */\n", "no marked block for `a.yml'"),
        ("<style></style>\n", "no marked block for `a.yml'"),
    ],
)
def test_refresh_rejects_missing_duplicated_or_nested_markers(text: str, message: str) -> None:
    with pytest.raises(PageError, match=message):
        refresh_page(text, {"a.yml": ["x"]})


def test_refresh_reports_an_undeclared_block_only_when_exhaustive() -> None:
    text = ("/* palette: a.yml */\nold\n/* palette: end */\n"
            "/* palette: b.yml */\nkept\n/* palette: end */\n")
    assert refresh_page(text, {"a.yml": ["new"]}) == text.replace("old", "new")
    with pytest.raises(PageError, match="block of `b.yml' names no palette declared"):
        refresh_page(text, {"a.yml": ["new"]}, exhaustive=True)


def test_marked_blocks_read_the_label_before_the_note() -> None:
    blocks, problems = marked_blocks(["  /* palette: x/palette.yml -- old note */", "/* palette: end */"])
    assert problems == []
    assert [(b.label, b.indent, b.opening, b.closing) for b in blocks] == [
        ("x/palette.yml", "  ", 0, 1)
    ]


@pytest.mark.parametrize("label", ["end", "a -- b", " padded"])
def test_a_label_that_a_marker_cannot_hold_is_rejected(label: str) -> None:
    assert label_problem(label) is not None


def test_css_page_refreshes_a_page_in_place(tmp_path: Path) -> None:
    _consumer(tmp_path)
    target = tmp_path / "site" / "index.html"
    args = ["--root", str(tmp_path), "--spec", str(tmp_path / "style" / "palette.yml"),
            "--css-page", str(target)]
    assert build_cli.main([*args, "--check"]) == 1
    assert _read(target) == PAGE                                          # --check writes nothing
    assert build_cli.main(args) == 0
    refreshed = _read(target)
    assert "    /* palette: style/palette.yml -- note kept by the consumer */\r\n" in refreshed
    assert "    /* Generated from style/palette.yml by chromata-build." in refreshed
    assert "      --bg: #FFFFFF;\r\n" in refreshed and "        --bg: #111111;\r\n" in refreshed
    assert "stale line" not in refreshed
    assert refreshed.endswith("  body { margin: 0 }\r\n</style>\r\n</html>")   # no final newline added
    assert build_cli.main([*args, "--check"]) == 0
    assert build_cli.main(args) == 0 and _read(target) == refreshed      # idempotent


@pytest.mark.parametrize(
    ("page_text", "extra"),
    [
        ("<style></style>\n", []),                                       # no markers
        (PAGE.replace("    /* palette: end */\r\n", ""), []),            # no closing marker
        (PAGE, ["--source-label", "end"]),                               # reserved label
        (PAGE, ["--css-output", "$PAGE"]),                               # a file target and a page
    ],
)
def test_css_page_rejects_an_unusable_page(tmp_path: Path, page_text: str, extra: list[str]) -> None:
    _consumer(tmp_path)
    target = _write(tmp_path / "site" / "index.html", page_text)
    options = [str(target) if value == "$PAGE" else value for value in extra]
    args = ["--root", str(tmp_path), "--spec", str(tmp_path / "style" / "palette.yml"),
            "--css-page", str(target), *options]
    assert build_cli.main(args) == 2
    assert _read(target) == page_text
    assert not (tmp_path / "style" / "colors-roles.tex").exists()       # nothing written


def test_css_page_requires_css_bindings(tmp_path: Path) -> None:
    _consumer(tmp_path)
    args = ["--root", str(tmp_path), "--spec", str(tmp_path / "hues" / "palette.yml"),
            "--css-page", str(tmp_path / "site" / "index.html")]
    assert build_cli.main(args) == 2


def test_manifest_builds_and_checks_every_palette_in_one_run(tmp_path: Path) -> None:
    _consumer(tmp_path)
    manifest = _write(tmp_path / "chromata.yml", MANIFEST)
    args = ["--root", str(tmp_path), "--config", str(manifest)]
    targets = [tmp_path / "hues" / "colors-values.tex", tmp_path / "style" / "colors-roles.tex",
               tmp_path / "concepts" / "roles.tex", tmp_path / "site" / "index.html"]
    assert build_cli.main([*args, "--check"]) == 1
    assert not any(target.exists() for target in targets[:3])
    assert build_cli.main(args) == 0
    assert all(target.exists() for target in targets)
    assert "--signal" not in _read(targets[3])                           # declared for no page
    snapshot = [_read(target) for target in targets]
    assert build_cli.main([*args, "--check"]) == 0
    assert build_cli.main(args) == 0
    assert [_read(target) for target in targets] == snapshot
    _write(tmp_path / "hues" / "palette.yml", HUES.replace("FFFFFF", "FAFAFA"))
    assert build_cli.main([*args, "--check"]) == 1                       # values and page are stale


def test_manifest_refreshes_two_palettes_in_one_page(tmp_path: Path) -> None:
    _consumer(tmp_path)
    two = PAGE + "\r\n/* palette: concepts/palette.yml */\r\n/* palette: end */\r\n"
    target = _write(tmp_path / "site" / "index.html", two)
    manifest = _write(tmp_path / "chromata.yml", MANIFEST.replace(
        "    roles_output: concepts/roles.tex\n",
        "    roles_output: concepts/roles.tex\n    css_pages: [site/index.html]\n"))
    assert build_cli.main(["--root", str(tmp_path), "--config", str(manifest)]) == 0
    refreshed = _read(target)
    assert "--bg: #FFFFFF;" in refreshed and "--signal: #025F99;" in refreshed


@pytest.mark.parametrize(
    ("edited", "old", "new", "message"),
    [
        ("style/palette.yml", "level: style", "level: bogus", "schema violation"),
        ("chromata.yml", "concepts/roles.tex", "style/colors-roles.tex", "declared twice"),
        ("chromata.yml", "concepts/roles.tex", "hues/palette.yml", "palette input"),
        ("chromata.yml", "spec: concepts/palette.yml", "spec: ../outside/palette.yml",
         "escapes the resource root"),
        ("chromata.yml", "chromata:build-manifest@1", "chromata:build-manifest@2", "schema violation"),
        ("chromata.yml", "[site/index.html]", "[site/absent.html]", "no such page"),
    ],
)
def test_manifest_rejects_an_invalid_run_and_writes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], edited: str, old: str, new: str,
    message: str,
) -> None:
    _consumer(tmp_path)
    manifest = _write(tmp_path / "chromata.yml", MANIFEST)
    target = tmp_path / edited
    _write(target, _read(target).replace(old, new))
    assert build_cli.main(["--root", str(tmp_path), "--config", str(manifest)]) == 2
    assert message in capsys.readouterr().err
    assert not (tmp_path / "hues" / "colors-values.tex").exists()       # the valid palettes too
    assert _read(tmp_path / "site" / "index.html") == PAGE


def test_manifest_rejects_a_block_of_an_undeclared_palette(tmp_path: Path) -> None:
    _consumer(tmp_path)
    _write(tmp_path / "site" / "index.html",
           PAGE + "\r\n/* palette: concepts/palette.yml */\r\n/* palette: end */\r\n")
    manifest = _write(tmp_path / "chromata.yml", MANIFEST)
    assert build_cli.main(["--root", str(tmp_path), "--config", str(manifest)]) == 2


@pytest.mark.parametrize(
    "extra",
    [["--css-page", "site/index.html"], ["--roles-prefix", "house-"], ["--tex-name", "a=b"]],
)
def test_manifest_excludes_per_palette_options(tmp_path: Path, extra: list[str]) -> None:
    _consumer(tmp_path)
    manifest = _write(tmp_path / "chromata.yml", MANIFEST)
    assert build_cli.main(["--root", str(tmp_path), "--config", str(manifest), *extra]) == 2


def test_config_and_spec_are_exclusive() -> None:
    parser = build_cli.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--root", ".", "--spec", "a.yml", "--config", "m.yml"])
    assert parser.parse_args(["-c", "m.yml"]).config == Path("m.yml")


@pytest.mark.parametrize(
    ("retired", "name"),
    [(["--manifest", "chromata.yml"], "--manifest"),
     (["--spec", "p.yml", "--values-out", "v.tex"], "--values-out"),
     (["--spec", "p.yml", "--roles-out", "r.tex"], "--roles-out"),
     (["--spec", "p.yml", "--css-out", "p.css"], "--css-out")],
)
def test_retired_option_names_are_rejected(
    capsys: pytest.CaptureFixture[str], retired: list[str], name: str
) -> None:
    with pytest.raises(SystemExit) as exit_info:
        build_cli.build_parser().parse_args(["--root", ".", *retired])
    assert exit_info.value.code == 2
    assert f"unrecognized arguments: {name}" in capsys.readouterr().err


def test_retired_manifest_keys_break_the_schema() -> None:
    entry = {"spec": "style/palette.yml", "roles_out": "out/roles.tex"}
    assert schema_violations(MANIFEST_SCHEMA, {"_schema": "chromata:build-manifest@1", "palettes": [entry]}) != []


@pytest.mark.parametrize("place", ["chromata.yml", "config/tools/chromata.yml"])
def test_settings_file_is_found_from_a_subfolder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, place: str
) -> None:
    _consumer(tmp_path)
    _write(tmp_path / place, MANIFEST)
    monkeypatch.delenv("CHROMATA_ROOT", raising=False)
    monkeypatch.chdir(tmp_path / "style")
    assert build_cli.main([]) == 0
    assert (tmp_path / "concepts" / "roles.tex").exists()                 # paths from the root
    assert build_cli.main(["--check"]) == 0


def test_settings_file_follows_the_root_variable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _consumer(tmp_path)
    _write(tmp_path / "config" / "tools" / "chromata.yml", MANIFEST)
    elsewhere = tmp_path.parent / f"{tmp_path.name}-elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("CHROMATA_ROOT", str(tmp_path))
    assert build_cli.main([]) == 0
    assert (tmp_path / "concepts" / "roles.tex").exists()


def test_two_settings_files_are_an_error_naming_both(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _consumer(tmp_path)
    _write(tmp_path / "chromata.yml", MANIFEST)
    _write(tmp_path / "config" / "tools" / "chromata.yml", MANIFEST)
    assert build_cli.main(["--root", str(tmp_path)]) == 2
    error = capsys.readouterr().err
    assert str(tmp_path / "chromata.yml") in error
    assert str(tmp_path / "config" / "tools" / "chromata.yml") in error
    assert not (tmp_path / "concepts" / "roles.tex").exists()


def test_without_spec_or_settings_file_nothing_is_built(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert build_cli.main(["--root", str(tmp_path)]) == 2
    assert "nothing to build" in capsys.readouterr().err


def test_config_path_is_relative_to_the_current_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _consumer(tmp_path)
    _write(tmp_path / "settings" / "palettes.yml", MANIFEST)
    monkeypatch.chdir(tmp_path / "settings")
    assert build_cli.main(["-r", str(tmp_path), "-c", "palettes.yml"]) == 0
    assert (tmp_path / "concepts" / "roles.tex").exists()                 # paths from the root


def test_manifest_reports_a_missing_or_malformed_file(tmp_path: Path) -> None:
    args = ["--root", str(tmp_path), "--config"]
    assert build_cli.main([*args, str(tmp_path / "absent.yml")]) == 2
    malformed = _write(tmp_path / "chromata.yml", "palettes: [\n")
    assert build_cli.main([*args, str(malformed)]) == 2


def test_manifest_schema_admits_every_per_palette_setting() -> None:
    entry = {
        "spec": "style/palette.yml",
        "values_output": "out/values.tex",
        "roles_output": "out/roles.tex",
        "css_output": "out/palette.css",
        "css_pages": ["site/index.html"],
        "source_label": "house:style",
        "values_prefix": "house-hue-",
        "roles_prefix": "house-",
        "tex_names": {"pagebg": "page-ground"},
    }
    assert schema_violations(MANIFEST_SCHEMA, {"_schema": "chromata:build-manifest@1", "palettes": [entry]}) == []
    assert schema_violations(MANIFEST_SCHEMA, {"_schema": "chromata:build-manifest@1", "palettes": [
        {**entry, "spec": "/absolute/palette.yml"}]}) != []
    assert schema_violations(MANIFEST_SCHEMA, {"_schema": "chromata:build-manifest@1", "palettes": [
        {**entry, "source_label": "bad*/label"}]}) != []


FORMATS = [
    (PALETTE_SCHEMA, "chromata:palette@1", {"level": "style"}),
    (MANIFEST_SCHEMA, "chromata:build-manifest@1", {"palettes": [{"spec": "a/palette.yml"}]}),
]


@pytest.mark.parametrize(("schema", "identifier", "body"), FORMATS)
def test_the_identifier_of_the_format_is_accepted(
    schema: str, identifier: str, body: dict[str, object]
) -> None:
    assert schema_violations(schema, {"_schema": identifier, **body}) == []


@pytest.mark.parametrize(("schema", "identifier", "body"), FORMATS)
@pytest.mark.parametrize(
    ("declared", "message"),
    [
        ({}, "_schema: absent; write _schema: {identifier} as the first key"),
        ({"_schema": "chromata:other@1"}, "_schema: chromata:other@1, expected {identifier}"),
        ({"schema_version": 1}, "schema_version: retired; write _schema: {identifier} as the first key"),
    ],
)
def test_a_record_of_another_format_names_the_value_to_write(
    schema: str, identifier: str, body: dict[str, object], declared: dict[str, object],
    message: str,
) -> None:
    expected = message.format(identifier=identifier)
    assert schema_violations(schema, {**declared, **body}) == [expected]


def test_a_file_of_the_retired_format_stops_with_status_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = _write(tmp_path / "chromata.yml", "schema_version: 1\npalettes: []\n")
    palette = _write(tmp_path / "hues.palette.yml", "schema_version: 1\nlevel: hues\n")
    assert build_cli.main(["--root", str(tmp_path), "--config", str(manifest)]) == 2
    assert "write _schema: chromata:build-manifest@1" in capsys.readouterr().err
    assert build_cli.main(["--root", str(tmp_path), "--spec", str(palette)]) == 2
    assert "write _schema: chromata:palette@1" in capsys.readouterr().err
