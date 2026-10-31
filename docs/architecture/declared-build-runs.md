# Declared build runs

A consumer of Chromata keeps its palettes, LaTeX layers and web pages in one repository. Before
this record, `chromata-build` projected one palette per run and wrote a CSS block only as a
standalone file. A consumer therefore needed its own script to keep every output current and to
refresh the CSS block embedded in a web page. This record fixes how Chromata covers both needs
without taking over the discovery of the consumer's files.

## Decision

1. **The consumer declares every input.** `chromata-build --manifest FILE` reads a build manifest,
   a YAML record under the installed `build-manifest.schema.yaml`. The manifest lists each palette
   with the settings that `chromata-build --spec` accepts. Chromata never searches the disk for
   palettes or pages, so a new palette enters a run only through the manifest.
2. **Manifest paths are relative to `--root` and stay inside it.** The resource root already
   resolves palette references and labels generated files. The same base therefore gives one
   meaning to a manifest on every machine.
3. **A marked page block belongs to its consumer, and only its body is generated.** `--css-page`,
   or the `css_pages` key of a manifest entry, names a page holding one block of the palette. The
   block opens with `/* palette: LABEL */`, where an optional note may follow ` -- `, and closes with
   `/* palette: end */`. A refresh rewrites only the lines between the two markers. Every other
   byte and every line ending stays unchanged. The generated body opens on its own provenance
   comment, since the markers are never rewritten.
4. **A malformed page is rejected.** A missing closing marker, a closing marker without a block,
   an opening marker inside a block, two blocks of one palette, or no block for a requested
   palette each stops the run. Under a manifest, a block of a palette that no entry declares for
   that page also stops the run. A misspelt label would otherwise leave its block silently stale.
5. **A run is planned in full before any target is written.** Each palette is loaded, each request
   is checked alone and against the others, and every target is rendered first. Any problem
   writes nothing and exits with status 2. Otherwise, `--check` exits with 1 when a target is
   stale, and 0 when every target is current.

## Rejected routes

- **Discovery by pattern or by repository scan.** A glob or a Git listing would select inputs
  from the state of the disk, which the [source-boundary record](source-boundary.md) assigns to
  the consumer. An explicit list also carries the per-palette settings that a pattern cannot.
- **Regenerating the markers with the body.** Rewriting the opening marker would overwrite a note
  of the consumer, and it would change bytes outside the generated region.
- **Writing the valid palettes of a failing run.** A partial run leaves a mixture of current and
  stale outputs. Because consumers commit generated outputs, that mixture could be committed.

## Consequences

- A consumer that adopts the manifest adds each new palette and each new page to it.
- A page migrated from another generator keeps its old marker note until the consumer edits it.
  The generated provenance comment states the current generator in the meantime.
- Acceptance tests remain per palette, through `chromata-check`. A manifest run checks that the
  projections are current, not that the colours pass their tests.
