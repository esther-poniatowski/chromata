# Chromata

Chromata validates colour-palette specifications and produces the files that consumers load. The
package provides three independent commands:

- `chromata-build` generates deterministic LaTeX and CSS projections;
- `chromata-check` applies declared separation and contrast criteria;
- `chromata-recolour` repaints declared two-colour raster assets.

The repository is private. No licence to redistribute or modify its contents is granted.

## Ownership boundary

Chromata owns the palette schema, colour calculations, projections, proof sheets, and raster
transformations. A consumer owns its palette records, generated outputs, and repository rules.
For example, a rule that forbids raw `\definecolor` declarations belongs to the repository that
adopts that rule.

Dependency managers resolve external resources before invoking Chromata. The package accepts a
local root or a resolver implementation; it does not read a dependency manager's cache layout.
The [source-boundary record](docs/architecture/source-boundary.md) fixes this separation.

The `examples/` folder contains one valid record for each palette level. The style example extends
the hue example, and the concept example extends the style example.

## Installation

Install the core package for palette compilation and checking:

```sh
python -m pip install .
```

Install the optional raster dependencies when `chromata-recolour` is required:

```sh
python -m pip install '.[raster]'
```

## Command examples

Each command receives an explicit palette and resource root. The build command writes its LaTeX
layers beside the specification unless explicit targets are supplied.

```sh
chromata-build --root . --spec style/palette.yml
chromata-build --root . --spec style/palette.yml --check
chromata-check --root . --spec style/palette.yml
chromata-recolour --root . --spec style/palette.yml --source images/source --out images/generated
```

`--values-prefix house-hue-` and `--roles-prefix house-` place generated TeX names in
separate value and role namespaces. Explicit `--values-out`, `--roles-out`, and `--css-out`
arguments control the projection targets. Repeated `--tex-name SOURCE=TARGET` arguments preserve a
consumer interface whose public name differs from the palette name.

Pass each resolved external file as `--resource <logical-reference>=<resolved-path>`. Then,
`--resource` binds the logical `extends` value to the supplied path. Without a binding, Chromata
resolves the value relative to `--root`. From a bound palette, Chromata resolves a sibling path
within the bound file's directory.

Generated files name their source relative to `--root`. When the logical resource root differs
from the desired provenance label, `--source-label` supplies that stable label explicitly.

## Verification

Install the development extras in a dedicated environment, then run:

```sh
python -m pytest
python -m ruff check src tests
python -m build
```
