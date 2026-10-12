"""
Palette tools: measure a colour palette written in LaTeX, and repaint raster assets into it.

The package serves any document whose colours are declared as ``\\definecolor`` and ``\\colorlet``
lines. A consumer owns its palette files and a TOML specification of its acceptance tests; the
package owns only the colour science and the procedures.

Modules
-------
colour
    Colour conversions, perceptual distance, contrast, and colour-vision simulation.
latex_palette
    Reading ``token -> RRGGBB`` out of LaTeX sources.
spec
    The consumer's specification: acceptance tests and recolouring rows, loaded from TOML.
report
    The acceptance tests applied to a palette.
proof
    A self-contained LaTeX proof sheet showing every token under each vision mode.
recolour
    Repainting two-colour raster pictures into two palette tokens.
"""
