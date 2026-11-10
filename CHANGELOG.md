# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

The command lines follow the workspace
[command-line conventions](https://github.com/esther-poniatowski/keystone/blob/main/docs/internals/cli-conventions.md).
Each renamed name loses its former name in this release, without an alias.

### Added
- `-r`, `--root` is optional on the three commands. Without it, the root is `CHROMATA_ROOT`, else
  the nearest ancestor of the current folder that holds `config/tools/chromata.yml` or
  `chromata.yml`, else the current folder.
- Without `--spec`, `chromata-build` reads its settings file, the build manifest `chromata.yml`,
  from `config/tools/chromata.yml` or `chromata.yml` below the root. A root holding both is an
  error that names both; a root holding neither is an error, since nothing is declared to build.
- `chromata-recolour` stops with status 2, writing nothing, when a repainted picture would leave
  `--output-dir` or overwrite a source picture.

### Changed
- `chromata-build --manifest` is renamed `-c`, `--config`.
- `chromata-build --values-out`, `--roles-out` and `--css-out` are renamed `--values-output`,
  `--roles-output` and `--css-output`, and the manifest keys `values_out`, `roles_out` and
  `css_out` are renamed `values_output`, `roles_output` and `css_output`.
- `chromata-recolour --out` is renamed `--output-dir`, the name that the conventions reserve for a
  folder of several output files. `--out` is no longer accepted.
- The commands no longer accept an abbreviation of an option, so that no prefix revives a retired
  name such as `--out`.
- A relative path given to `--resource` is read from the current folder, instead of being rejected.
