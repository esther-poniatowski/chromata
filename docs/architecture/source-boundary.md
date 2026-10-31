# Source boundary

Chromata owns one transformation family: a palette specification becomes checked colour values,
LaTeX or CSS projections, proof sheets, and optional recoloured images. These operations share the
same schema and colour model, so they change as one release unit.

## Owned sources

The repository owns:

- the versioned palette and build-manifest schemas and their loaders;
- the resolver protocol for referenced palettes;
- colour conversion, contrast, perceptual distance, and vision simulation;
- deterministic LaTeX and CSS projection, including the refresh of a marked block inside a page;
- acceptance reports and proof sheets;
- raster recolouring based on a palette record;
- the three commands that expose those operations.

## Consumer-owned sources

A consuming repository owns:

- palette records and their semantic roles;
- generated projections and recoloured images;
- discovery of palette and artifact files;
- rules that prohibit colour declarations outside a palette;
- exceptions for venue templates, archives, or other repository classes.

Therefore, Chromata does not scan a Git repository. Its commands require explicit input and
output locations, given either as command options or as the entries of a build manifest written by
the consumer. A consumer may also implement a repository adapter that discovers those inputs and
calls the package API. The [declared-build-runs record](declared-build-runs.md) fixes the manifest
and the refresh of a marked page block.

## Dependency boundary

A dependency manager owns resource acquisition, commit selection, snapshots, and cache locations.
The dependency boundary supplies each resolved file to Chromata through `ResourceResolver`.

Two resolvers confine Chromata to explicitly selected files. `LocalResolver` resolves relative paths
within its configured root. By contrast, `MappedResolver` binds each exact logical name to a resolved
file. For a nested `extends` value, `MappedResolver` confines lookup to the mapped resource directory.
Chromata must not import a dependency manager or inspect its storage.

## Version-one restrictions

Schema version 1 admits one named alternate rendering, `dark`, and maps it to the corresponding CSS
media query. A later schema version must generalize this field before another rendering mode is
accepted. The restriction is explicit so that a new mode cannot be silently omitted from CSS.

Raster dependencies remain optional. Palette compilation and checking therefore install without
NumPy or Pillow.
