"""
Palette tools: load a colour palette, generate its LaTeX and CSS, measure it, and repaint raster
assets into it.

A consumer owns one ``palette.yml`` under ``utils/schemas/palette.schema.yaml``, holding its tokens,
roles, modes and acceptance tests; the package owns only the colour science and the procedures.

Modules
-------
colour
    Colour conversions, perceptual distance, contrast, and colour-vision simulation.
latex_palette
    Reading ``token -> RRGGBB`` out of LaTeX sources, such as a candidate scheme.
spec
    A palette file, loaded and checked: tokens, roles, modes, CSS names, tests and recolouring rows.
emit
    The LaTeX layers and the CSS block generated from a palette.
report
    The acceptance tests applied to a palette.
proof
    A self-contained LaTeX proof sheet showing every token under each vision mode.
recolour
    Repainting two-colour raster pictures into two palette tokens.
"""
