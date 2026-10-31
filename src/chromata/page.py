"""
The marked CSS blocks of an existing web page, refreshed in place.

A consumer marks each block of a page with two comment lines. The opening marker names the source
label of the palette, optionally followed by a note after `` -- ``::

    /* palette: style/palette.yml */
    /* palette: style/palette.yml -- any note kept by the consumer */

The closing marker is ``/* palette: end */``. A refresh replaces only the lines between the two
markers. The markers themselves, every other line and every line ending stay byte for byte, so a
second refresh with the same palette changes nothing.

A page is rejected when a marker is missing, duplicated or nested: a block without a closing
marker, a closing marker without a block, an opening marker inside a block, two blocks naming one
palette, or no block for a requested palette.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

#: Label reserved by the closing marker.
END_LABEL = "end"

#: Separator between the label of an opening marker and the note of the consumer.
NOTE_SEPARATOR = " -- "

_MARKER_RE = re.compile(r"^(?P<indent>[ \t]*)/\* palette: (?P<rest>.*?)[ \t]*\*/[ \t]*$")


class PageError(ValueError):
    """Raised when the markers of a page do not delimit one block per requested palette."""

    def __init__(self, problems: Sequence[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = tuple(problems)


@dataclass(frozen=True)
class MarkedBlock:
    """One marked block: the label of its opening marker and the indices of its two markers."""

    label: str
    indent: str
    opening: int
    closing: int


def label_problem(label: str) -> str | None:
    """
    Return why a source label cannot be written in an opening marker, or ``None``.

    Examples
    --------
    >>> label_problem("style/palette.yml") is None
    True
    >>> label_problem("end")
    "the label `end' is reserved by the closing marker"
    """
    if label == END_LABEL:
        return f"the label `{END_LABEL}' is reserved by the closing marker"
    if NOTE_SEPARATOR in label or label != label.strip():
        return f"a marker label cannot contain `{NOTE_SEPARATOR}' or surrounding spaces"
    return None


def _marker(line: str) -> tuple[str, str] | None:
    """Return ``(indent, label)`` of a marker line, the label of a closing marker being ``end``."""
    match = _MARKER_RE.match(line.rstrip("\r\n"))
    if match is None:
        return None
    return match["indent"], match["rest"].split(NOTE_SEPARATOR, 1)[0].strip()


def marked_blocks(lines: Sequence[str]) -> tuple[list[MarkedBlock], list[str]]:
    """
    Parse the marked blocks of a page.

    Parameters
    ----------
    lines : Sequence[str]
        The lines of the page, with or without their line endings.

    Returns
    -------
    tuple[list[MarkedBlock], list[str]]
        The well-formed blocks in page order, and the structural problems found.
    """
    blocks: list[MarkedBlock] = []
    problems: list[str] = []
    open_block: tuple[int, str, str] | None = None
    for index, line in enumerate(lines):
        marker = _marker(line)
        if marker is None:
            continue
        indent, label = marker
        if label == END_LABEL:
            if open_block is None:
                problems.append(f"line {index + 1}: closing marker without an opening marker")
                continue
            start, start_indent, start_label = open_block
            blocks.append(MarkedBlock(start_label, start_indent, start, index))
            open_block = None
        elif open_block is not None:
            problems.append(f"line {index + 1}: opening marker of `{label}' inside the block "
                            f"of `{open_block[2]}' opened on line {open_block[0] + 1}")
        else:
            open_block = (index, indent, label)
    if open_block is not None:
        problems.append(f"line {open_block[0] + 1}: block of `{open_block[2]}' "
                        "has no closing marker")
    return blocks, problems


def _newline(line: str) -> str:
    """Return the line ending of ``line``, defaulting to a line feed."""
    stripped = line.rstrip("\r\n")
    return line[len(stripped):] or "\n"


def refresh_page(
    text: str,
    bodies: Mapping[str, Sequence[str]],
    *,
    exhaustive: bool = False,
) -> str:
    """
    Replace the body of each requested block of a page.

    Parameters
    ----------
    text : str
        The page, read without newline translation.
    bodies : Mapping[str, Sequence[str]]
        The lines placed between the markers of each requested label, without indentation or
        line endings. Each line receives the indentation of its opening marker and the line
        ending of that marker.
    exhaustive : bool
        Whether every block of the page must be requested. A consumer that declares every
        palette of a page sets it, so that a block naming an undeclared palette is reported.

    Returns
    -------
    str
        The refreshed page.

    Raises
    ------
    PageError
        If a marker is missing, duplicated or nested.

    Examples
    --------
    >>> page = "<style>\\n/* palette: p.yml */\\nold\\n/* palette: end */\\n</style>\\n"
    >>> refresh_page(page, {"p.yml": [":root {}"]})
    '<style>\\n/* palette: p.yml */\\n:root {}\\n/* palette: end */\\n</style>\\n'
    """
    lines = text.splitlines(keepends=True)
    blocks, problems = marked_blocks(lines)
    by_label: dict[str, list[MarkedBlock]] = {}
    for block in blocks:
        by_label.setdefault(block.label, []).append(block)
    for label, found in by_label.items():
        if len(found) > 1:
            places = ", ".join(str(block.opening + 1) for block in found)
            problems.append(f"block of `{label}' is marked more than once, on lines {places}")
        elif exhaustive and label not in bodies:
            problems.append(f"line {found[0].opening + 1}: block of `{label}' "
                            "names no palette declared for this page")
    opened = {marker[1] for line in lines if (marker := _marker(line)) is not None}
    problems.extend(f"no marked block for `{label}'" for label in bodies if label not in opened)
    if problems:
        raise PageError(problems)

    out: list[str] = []
    cursor = 0
    for block in blocks:
        if block.label not in bodies:
            continue
        newline = _newline(lines[block.opening])
        out.extend(lines[cursor:block.opening + 1])
        out.extend(block.indent + line + newline for line in bodies[block.label])
        cursor = block.closing
    out.extend(lines[cursor:])
    return "".join(out)
