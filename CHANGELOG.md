# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

### Changed
- `chromata-recolour` names its folder of repainted pictures `--output-dir`, the name that the
  workspace command-line conventions reserve for a folder of several output files.

### Deprecated
- `chromata-recolour --out` remains accepted for one release as a hidden alias of `--output-dir`,
  and prints a warning naming `--output-dir`. The following release removes it.
