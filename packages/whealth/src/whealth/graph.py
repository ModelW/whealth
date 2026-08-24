"""Dependency graph resolution for health controls."""

from __future__ import annotations

import dataclasses
from enum import Enum, auto

from whealth.registry import ControlInfo


class DependencyIssue(Enum):
    """Why a dependency was dropped from the resolved graph."""

    UNRESOLVED = auto()
    """The dependency reference does not point to any known control."""
    CYCLE = auto()
    """The dependency would create a cycle in the dependency graph."""


@dataclasses.dataclass(frozen=True)
class DependencyNote:
    """A dependency that was dropped, together with the reason."""

    control_app_label: str
    control_slug: str
    dependency_ref: str
    reason: DependencyIssue


def _resolve_dep(raw: str, app_label: str) -> tuple[str, str]:
    """Resolve a ``depends_on`` entry to (app_label, slug)."""
    if "." in raw:
        parts = raw.split(".", 1)
        return (parts[0], parts[1])
    return (app_label, raw)


def resolve_dependencies(
    controls: list[ControlInfo],
) -> tuple[list[ControlInfo], list[DependencyNote]]:
    """Produce a DAG-safe list of controls.

    Builds a graph from the ``depends_on`` declarations and uses a spanning
    tree to drop edges that would introduce cycles.  Dependencies that
    reference unknown controls are also reported.

    Parameters
    ----------
    controls : list of ControlInfo

    Returns
    -------
    tuple of (list[ControlInfo], list[DependencyNote])
        The first list contains every control, each with a ``depends_on``
        tuple that is guaranteed acyclic.  The second list records every
        dependency that was dropped and why.
    """
    from whealth.registry import Manifest

    lookup: dict[tuple[str, str], ControlInfo] = {
        (c.app_label, c.slug): c for c in controls
    }

    graph: dict[tuple[str, str], list[tuple[str, str]]] = {key: [] for key in lookup}

    notes: list[DependencyNote] = []

    for c in controls:
        key = (c.app_label, c.slug)
        for dep_raw in c.manifest.depends_on:
            dep_key = _resolve_dep(dep_raw, c.app_label)

            if dep_key not in lookup:
                notes.append(
                    DependencyNote(
                        control_app_label=c.app_label,
                        control_slug=c.slug,
                        dependency_ref=dep_raw,
                        reason=DependencyIssue.UNRESOLVED,
                    )
                )
                continue

            graph[key].append(dep_key)
            if _has_cycle(graph):
                graph[key].pop()
                notes.append(
                    DependencyNote(
                        control_app_label=c.app_label,
                        control_slug=c.slug,
                        dependency_ref=dep_raw,
                        reason=DependencyIssue.CYCLE,
                    )
                )

    dropped_refs: set[tuple[str, str, str, DependencyIssue]] = {
        (d.control_app_label, d.control_slug, d.dependency_ref, d.reason) for d in notes
    }

    safe_controls: list[ControlInfo] = []
    for c in controls:
        safe_deps = [
            dep
            for dep in c.manifest.depends_on
            if (c.app_label, c.slug, dep, DependencyIssue.CYCLE) not in dropped_refs
        ]
        safe_manifest = Manifest(
            depends_on=tuple(safe_deps),
            title=c.manifest.title,
            is_ignorable=c.manifest.is_ignorable,
            impact=c.manifest.impact,
            meta=c.manifest.meta,
        )
        safe_controls.append(
            ControlInfo(
                app_label=c.app_label,
                slug=c.slug,
                title=c.title,
                module=c.module,
                control_class=c.control_class,
                manifest=safe_manifest,
                readme=c.readme,
            )
        )

    return safe_controls, notes


def _has_cycle(
    graph: dict[tuple[str, str], list[tuple[str, str]]],
) -> bool:
    """Return ``True`` if *graph* contains a directed cycle."""
    WHITE, GRAY, BLACK = 0, 1, 2
    colour: dict[tuple[str, str], int] = {n: WHITE for n in graph}

    def dfs(node: tuple[str, str]) -> bool:
        colour[node] = GRAY
        for neighbour in graph.get(node, []):
            if colour[neighbour] == GRAY:
                return True
            if colour[neighbour] == WHITE and dfs(neighbour):
                return True
        colour[node] = BLACK
        return False

    return any(colour[node] == WHITE and dfs(node) for node in graph)
