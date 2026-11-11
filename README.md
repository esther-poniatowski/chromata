# Chromata

Chromata validates colour-palette specifications and produces the files that consumers load. The
package provides three independent commands:

- `chromata-build` generates deterministic LaTeX and CSS projections;
- `chromata-check` applies declared separation and contrast criteria;
- `chromata-recolour` repaints declared two-colour raster assets.

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

Each command receives an explicit palette. The build command writes its LaTeX layers beside the
specification unless explicit targets are supplied.

```sh
chromata-build --spec style/palette.yml
chromata-build --spec style/palette.yml --check
chromata-check --spec style/palette.yml
chromata-recolour --spec style/palette.yml --source images/source --output-dir images/generated
```

Every command resolves its resource root in this order: `-r`, `--root`; the environment variable
`CHROMATA_ROOT`; the nearest ancestor of the current folder that holds the configuration file
`chromata.yml`, in its `config/tools/` or at its own level; the current folder. A path given on the
command line is relative to the current folder.

`--values-prefix house-hue-` and `--roles-prefix house-` place generated TeX names in
separate value and role namespaces. Explicit `--values-output`, `--roles-output`, and
`--css-output` arguments control the projection targets. Repeated `--tex-name SOURCE=TARGET`
arguments preserve a consumer interface whose public name differs from the palette name.

Pass each resolved external file as `--resource <logical-reference>=<path>`, where a relative path
is read from the current folder. Then,
`--resource` binds the logical `extends` value to the supplied path. Without a binding, Chromata
resolves the value relative to `--root`. From a bound palette, Chromata resolves a sibling path
within the bound file's directory.

`--css-page PAGE` refreshes the CSS block of the palette inside an existing web page. The page
marks the block with `/* palette: LABEL */` and `/* palette: end */`, where `LABEL` is the source
label of the palette. A refresh rewrites only the lines between the markers, and fails when a
marker is missing or duplicated.

The configuration file of Chromata, `chromata.yml`, is a build manifest: it lists every palette of
a consumer, with the settings of each, so that one run builds or checks all of them with one exit
status. Without `--spec`, `chromata-build` reads the file named by `-c`, `--config`, else
`config/tools/chromata.yml` or `chromata.yml` below the root. A root holding both files is an
error that names both, and a root holding neither leaves nothing to build:

```sh
chromata-build --check
chromata-build --config settings/palettes.yml --check
```

```yaml
_schema: chromata:build-manifest@1
palettes:
  - spec: style/hues/palette.yml
  - spec: style/palette.yml
    css_pages: [site/index.html]
```

The paths of the configuration file are relative to the root, wherever the file lies. The
[declared-build-runs record](docs/architecture/declared-build-runs.md) fixes the manifest, the
marker syntax and the exit statuses.

`chromata-recolour` writes each repainted picture into `--output-dir`, and stops with status 2,
writing nothing, when a picture would leave that folder or overwrite a source picture.

Generated files name their source relative to `--root`. When the logical resource root differs
from the desired provenance label, `--source-label` supplies that stable label explicitly.

## Schema registry

The [schema registry](specs/schema-registry.yml) maps each format whose schema Chromata ships to that schema file. Kleisis generates the registry from the [resource record](specs/schema-resources.yml): run `kleisis materialize --root .` after a schema changes, and `kleisis check --root .` to confirm that the registry is current. A repository whose files declare a Chromata format names Chromata as a dependency in its own resource record, at a pinned commit, so that Ekphrasis validates those files in Obsidian.

## Verification

Install the development extras in a dedicated environment, then run:

```sh
python -m pytest
python -m ruff check src tests
python -m build
```

## License

The [license terms](LICENSE) apply under the General Public License, release 3 or any subsequent release.
