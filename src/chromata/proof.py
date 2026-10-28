"""
A self-contained LaTeX proof sheet: every token of a palette, under each vision mode.

The report gives numbers; the proof sheet shows them. Two swatches that are visibly the same colour
under tritanopia are a fact one can act on, whereas a distance of 0.03 must be trusted. The sheet
needs no file of the consumer to compile: every colour, including the simulated ones, is written into
it as a literal ``\\definecolor``.
"""

from __future__ import annotations

from chromata.colour import VISION_MODES, simulate
from chromata.spec import AcceptanceTests

_PREAMBLE = r"""\documentclass[10pt]{article}
\usepackage[a4paper,landscape,margin=10mm]{geometry}
\usepackage{xcolor}
\usepackage{tikz}
\pagestyle{empty}
\setlength{\parindent}{0pt}
\newcommand{\swatch}[2]{% #1 colour, #2 label
  \begin{tikzpicture}[baseline=(current bounding box.north)]
    \fill[proofground] (0,0) rectangle (2.55,1.15);
    \fill[#1] (0.1,0.1) rectangle (2.45,1.05);
    \node[anchor=north west,inner sep=0pt,font=\tiny] at (0,-0.08) {\texttt{#2}};
  \end{tikzpicture}\hspace{0.6mm}}
\newcommand{\heading}[1]{\par\vspace{3.5mm}{\bfseries\footnotesize #1}\par\vspace{1.2mm}}
"""


def _name(token: str, mode: str) -> str:
    # Simulated colours live under `token@mode', a namespace no document call site can reach.
    return token if mode == "normal" else f"{token}@{mode}"


def proof_sheet(palette: dict[str, str], label: str, tests: AcceptanceTests | None = None) -> str:
    """
    Write a proof sheet for a palette.

    Parameters
    ----------
    palette : dict[str, str]
        ``token -> RRGGBB``.
    label : str
        A name for the palette, printed as the title.
    tests : AcceptanceTests, optional
        When given, tokens are shown in the order of its groups, marks and fills; every other token
        follows.

    Returns
    -------
    str
        A complete LaTeX document.
    """
    sections: list[tuple[str, list[str]]] = []
    seen: set[str] = set()
    if tests is not None:
        ordered: list[tuple[str, tuple[str, ...]]] = [
            *tests.groups.items(), ("marks", tests.marks), ("fills and grounds", tests.fills)
        ]
        for title, group in ordered:
            present = [t for t in group if t in palette and t not in seen]
            seen.update(present)
            if present:
                sections.append((title, present))
    rest = [t for t in sorted(palette) if t not in seen]
    if rest:
        sections.append(("other tokens" if sections else "all tokens", rest))

    ground = tests.ground if tests is not None and tests.ground in palette else None
    out = [_PREAMBLE]
    out.append(
        f"\\definecolor{{proofground}}{{HTML}}{{{palette[ground] if ground else 'FFFFFF'}}}"
    )
    for token in sorted(palette):
        for mode in VISION_MODES:
            out.append(
                f"\\definecolor{{{_name(token, mode)}}}{{HTML}}{{{simulate(palette[token], mode)}}}"
            )
    out.append("\\begin{document}")
    out.append(f"{{\\Large\\bfseries Colour proof --- {label}}}\\par")
    out.append("{\\footnotesize Columns: " + ", ".join(VISION_MODES) + ".}\\par")
    for title, tokens in sections:
        out.append(f"\\heading{{{title}}}")
        for token in tokens:
            cells = "".join(
                f"\\swatch{{{_name(token, mode)}}}{{{token if mode == 'normal' else mode}}}"
                for mode in VISION_MODES
            )
            out.append(cells + "\\par\\vspace{0.6mm}")
    out.append("\\end{document}")
    return "\n".join(out) + "\n"
