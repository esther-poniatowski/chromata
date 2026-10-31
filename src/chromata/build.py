"""
The projections of one or more palettes, planned in full before any target is written.

A build request names one palette and the targets of its projections: the LaTeX layers, a
standalone CSS block, and the web pages whose marked block is refreshed in place. Planning loads
every palette, checks each request and the requests together, and renders the final text of every
target. A plan that holds a problem is never written, so a consumer cannot commit the outputs of a
partial build.

The requests come from the consumer, either as the options of one command or as the entries of a
build manifest. Chromata never searches the disk for palettes or pages.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from chromata.emit import (
    ROLES_FILE,
    VALUES_FILE,
    ProjectionError,
    TeXProjection,
    css_block,
    css_page_body,
    display_path,
    outputs,
)
from chromata.page import PageError, label_problem, refresh_page
from chromata.spec import PaletteSpec, ResourceResolver, SpecError, load_spec


@dataclass(frozen=True)
class BuildRequest:
    """One palette and the targets of its projections."""

    spec: Path
    values_out: Path | None = None
    roles_out: Path | None = None
    css_out: Path | None = None
    css_pages: tuple[Path, ...] = ()
    source_label: str | None = None
    values_prefix: str = ""
    roles_prefix: str = ""
    tex_names: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class BuildPlan:
    """The final text of every target of a run, or the problems that prevent the run."""

    texts: dict[Path, str] = field(default_factory=dict)
    #: Targets compared and written byte for byte, without newline translation.
    pages: frozenset[Path] = frozenset()
    palettes: int = 0
    problems: tuple[str, ...] = ()


def comment_label_problem(label: str) -> str | None:
    """Return why a source label would break a generated comment, or ``None``."""
    if not label or "\n" in label or "\r" in label or "*/" in label:
        return "source label cannot contain a line break or `*/'"
    return None


def shown(path: Path, root: Path) -> str:
    """Return a path relative to the resource root when it lies inside it."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _source_paths(spec: PaletteSpec) -> set[Path]:
    """Return every palette file loaded into one specification."""
    paths: set[Path] = set()
    current: PaletteSpec | None = spec
    while current is not None:
        paths.add(current.path.resolve())
        current = current.base
    return paths


def _request_problems(spec: PaletteSpec, request: BuildRequest, root: Path) -> list[str]:
    """Return the unsafe or ambiguous settings of one request."""
    problems: list[str] = []
    label = request.source_label
    if label is None:
        try:
            label = display_path(spec.path, root)
        except ValueError:
            problems.append("a palette outside the resource root requires a source label")
    elif (problem := comment_label_problem(label)) is not None:
        problems.append(problem)
    if request.values_out is not None and not spec.layers:
        problems.append("a value-layer target was given for a palette without value layers")
    if request.roles_out is not None and not spec.roles:
        problems.append("a role-layer target was given for a palette without roles")
    if (request.css_out is not None or request.css_pages) and not spec.css:
        problems.append("a CSS target requires a palette with CSS bindings")
    if request.css_pages and label is not None and (problem := label_problem(label)) is not None:
        problems.append(problem)
    sources = [source for source, _ in request.tex_names]
    duplicate_sources = {source for source in sources if sources.count(source) > 1}
    problems.extend(f"TeX name is mapped twice: {source}" for source in sorted(duplicate_sources))
    return problems


def _declared_targets(spec: PaletteSpec, request: BuildRequest) -> list[Path]:
    """Return the resolved file targets of one request, before any is merged with another."""
    folder = spec.path.parent
    targets: list[Path] = []
    if spec.layers:
        targets.append((request.values_out or folder / VALUES_FILE).resolve())
    if spec.roles:
        targets.append((request.roles_out or folder / ROLES_FILE).resolve())
    if request.css_out is not None:
        targets.append(request.css_out.resolve())
    return targets


def _read_exact(path: Path) -> str:
    """Read a page without newline translation."""
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def plan_build(
    requests: Sequence[BuildRequest],
    root: Path,
    resolver: ResourceResolver,
    *,
    exhaustive_pages: bool = False,
) -> BuildPlan:
    """
    Render every target of a run, or collect every problem that prevents it.

    Parameters
    ----------
    requests : Sequence[BuildRequest]
        The palettes of the run and the targets of their projections.
    root : Path
        The resource root, against which provenance labels are written.
    resolver : ResourceResolver
        The resolver of the palette references.
    exhaustive_pages : bool
        Whether every marked block of a requested page must name a requested palette. A build
        manifest sets it, since it declares every palette of the consumer.

    Returns
    -------
    BuildPlan
        The final text of each target when ``problems`` is empty.
    """
    problems: list[str] = []
    declared: list[Path] = []
    texts: dict[Path, str] = {}
    inputs: set[Path] = set()
    page_bodies: dict[Path, dict[str, list[str]]] = {}
    loaded = 0
    for request in requests:
        try:
            spec = load_spec(request.spec, root, resolver=resolver)
        except SpecError as error:
            problems.append(str(error))
            continue
        loaded += 1
        inputs |= _source_paths(spec)
        own = _request_problems(spec, request, root)
        if own:
            problems.extend(f"{shown(request.spec, root)}: {problem}" for problem in own)
            continue
        try:
            projection = TeXProjection.for_spec(
                spec,
                values_prefix=request.values_prefix,
                roles_prefix=request.roles_prefix,
                names=dict(request.tex_names),
            )
        except ProjectionError as error:
            problems.append(f"{shown(request.spec, root)}: {error}")
            continue
        rendered = outputs(
            spec,
            root,
            values_target=request.values_out,
            roles_target=request.roles_out,
            projection=projection,
            source_label=request.source_label,
        )
        label = request.source_label or display_path(spec.path, root)
        if request.css_out is not None:
            rendered[request.css_out] = css_block(spec, label, "") + "\n"
        if not rendered and not request.css_pages:
            problems.append(f"{shown(request.spec, root)}: the palette declares no projection")
        declared.extend(_declared_targets(spec, request))
        texts.update((target.resolve(), text) for target, text in rendered.items())
        for page in request.css_pages:
            bodies = page_bodies.setdefault(page.resolve(), {})
            if label in bodies:
                problems.append(f"{shown(page, root)}: two requests refresh the block of `{label}'")
            bodies[label] = css_page_body(spec, label)

    duplicates = {target for target in declared if declared.count(target) > 1}
    problems.extend(
        f"output target is declared twice: {shown(target, root)}" for target in sorted(duplicates)
    )
    problems.extend(
        f"output target is also a refreshed page: {shown(target, root)}"
        for target in sorted(set(declared) & set(page_bodies))
    )
    problems.extend(
        f"output target would overwrite a palette input: {shown(target, root)}"
        for target in sorted((set(declared) | set(page_bodies)) & inputs)
    )

    for page, bodies in page_bodies.items():
        if not page.is_file():
            problems.append(f"no such page: {shown(page, root)}")
            continue
        try:
            texts[page] = refresh_page(_read_exact(page), bodies, exhaustive=exhaustive_pages)
        except PageError as error:
            problems.extend(f"{shown(page, root)}: {problem}" for problem in error.problems)
    if problems:
        return BuildPlan(palettes=loaded, problems=tuple(problems))
    return BuildPlan(texts, frozenset(page_bodies), loaded)


def changed_targets(plan: BuildPlan) -> list[Path]:
    """Return the targets of a plan whose current contents differ from the planned text."""
    changed: list[Path] = []
    for target, text in plan.texts.items():
        if not target.exists():
            changed.append(target)
            continue
        exact = target in plan.pages
        current = _read_exact(target) if exact else target.read_text(encoding="utf-8")
        if current != text:
            changed.append(target)
    return changed


def write_targets(plan: BuildPlan, targets: Sequence[Path]) -> None:
    """Write the planned text of each target, creating its folder when needed."""
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("w", encoding="utf-8", newline="") as handle:
            handle.write(plan.texts[target])

