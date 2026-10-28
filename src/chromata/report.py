"""
The acceptance tests applied to a palette.

1. **Categorical separation.** Two colours a reader must tell apart need an OKLab distance at least
   ``de_floor``.
2. **Mark contrast.** A graphical mark needs a WCAG contrast at least ``contrast_floor`` on the page
   ground. Fills and washes are exempt and must carry a saturated stroke instead.
3. **Non-colour redundancy.** Test 1 is repeated under simulated colour-vision deficiency and under
   grayscale. A pair that separates only for trichromats is reported, and must carry its
   distinction on a non-colour channel.
4. **Ladder limit.** Two adjacent rungs of one ladder are not distinct, so no group may hold both.
5. **Pair contrast.** A mark drawn on a ground other than the page, such as text on a badge, needs
   the contrast floor on that ground.

The trichromatic separation, both contrast tests and the ladder limit are binding; the redundancy
test reports.
A mark listed under ``accepted`` is reported under the contrast floor without counting as a
failure. An acceptance that no longer applies counts as one: a stale acceptance would otherwise
license a later regression of the same token.
"""

from __future__ import annotations

import math
from itertools import combinations

from chromata.colour import VISION_MODES, contrast, delta_e, oklab, simulate
from chromata.spec import AcceptanceTests


def report(palette: dict[str, str], tests: AcceptanceTests, label: str) -> tuple[str, int]:
    """
    Apply the acceptance tests to a palette.

    Parameters
    ----------
    palette : dict[str, str]
        ``token -> RRGGBB``.
    tests : AcceptanceTests
        The consumer's tests.
    label : str
        A name for the palette, printed in the report header.

    Returns
    -------
    tuple[str, int]
        The report text, and the number of binding failures.
    """
    lines: list[str] = []
    failures = 0
    missing = sorted(tests.named_tokens() - palette.keys())
    if missing:
        lines.append(f"tokens named by the tests but absent from the palette: {', '.join(missing)}\n")
    for token in sorted(set(tests.accepted) - set(tests.marks)):
        lines.append(f"accepted token `{token}' is not a mark: the acceptance has nothing to license")
        failures += 1
    if tests.ground not in palette:
        lines.append(f"the ground token `{tests.ground}' is undefined: contrast cannot be measured")
        return "\n".join(lines), 1

    lines.append(f"=== palette: {label} ===\n")
    lines.append("--- token lightness and contrast on the page ground ---")
    lines.append(f"{'token':<16}{'hex':>8}{'OKLab L':>10}{'chroma':>9}{'on bg':>9}")
    for token in [tests.ground, *tests.marks, *tests.fills]:
        if token not in palette:
            continue
        value = palette[token]
        lightness, a, b = oklab(value)
        ratio = contrast(value, palette[tests.ground])
        flag = ""
        if token in tests.marks and ratio < tests.contrast_floor:
            if token in tests.accepted:
                flag = f"  -- accepted: {tests.accepted[token]}"
            else:
                flag = f"  << under {tests.contrast_floor:g}:1"
                failures += 1
        elif token in tests.accepted:
            flag = "  << accepted, but no longer under the floor: drop the acceptance"
            failures += 1
        lines.append(
            f"{token:<16}{value:>8}{lightness:>10.3f}{math.hypot(a, b):>9.3f}{ratio:>8.2f}:1{flag}"
        )

    if tests.pairs:
        lines.append("\n--- marks on their own ground ---")
        for mark, ground in tests.pairs:
            if mark not in palette or ground not in palette:
                continue
            ratio = contrast(palette[mark], palette[ground])
            flag = ""
            if ratio < tests.contrast_floor:
                flag = f"  << under {tests.contrast_floor:g}:1"
                failures += 1
            lines.append(f"{mark + ' on ' + ground:<34}{ratio:>8.2f}:1{flag}")

    # A pair may sit in several groups; each failing pair is counted once, so the total reports
    # the palette rather than the shape of the group table.
    counted: set[frozenset[str]] = set()
    for title, tokens in tests.groups.items():
        present = [t for t in tokens if t in palette]
        lines.append(f"\n--- {title} ---")
        lines.append(f"{'pair':<34}" + "".join(f"{m:>9}" for m in VISION_MODES))
        for x, y in combinations(present, 2):
            row = [
                delta_e(oklab(simulate(palette[x], mode)), oklab(simulate(palette[y], mode)))
                for mode in VISION_MODES
            ]
            mark = ""
            ladder_x, ladder_y = tests.ladder.get(x), tests.ladder.get(y)
            adjacent = (ladder_x is not None and ladder_y is not None
                        and ladder_x[0] == ladder_y[0] and abs(ladder_x[1] - ladder_y[1]) == 1)
            if adjacent:
                mark = f"  << adjacent rungs of `{ladder_x[0]}'"
                if frozenset({x, y}) not in counted:
                    counted.add(frozenset({x, y}))
                    failures += 1
            elif (channel := tests.exempt.get(frozenset({x, y}))) is not None:
                mark = f"  -- {channel}"
            elif row[0] < tests.de_floor:
                mark = f"  << under {tests.de_floor:g}"
                if frozenset({x, y}) not in counted:
                    counted.add(frozenset({x, y}))
                    failures += 1
            elif min(row[1:]) < tests.de_floor:
                mark = "  << colour alone is not enough"
            lines.append(f"{x + ' / ' + y:<34}" + "".join(f"{v:>9.3f}" for v in row) + mark)

    return "\n".join(lines), failures
