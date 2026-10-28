"""
Chromata loads a colour palette, generates its LaTeX and CSS projections, measures its acceptance
criteria, and repaints raster assets into its declared colours.

A consumer owns its palette specifications and generated files. Chromata owns the schema, colour
science and transformations. Repository discovery and policy remain with each consumer.

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
