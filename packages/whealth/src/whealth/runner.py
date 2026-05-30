"""Runner that executes all registered controls."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Literal

from whealth.graph import topological_sort

if TYPE_CHECKING:
    from whealth.base import Failure
    from whealth.registry import ControlRegistry


type RunResult = list[Failure] | Literal[False]
"""Outcome for a single control after a run pass.

* ``list[Failure]`` — control ran successfully (may be empty).
* ``False`` — control could not run because one or more dependencies
  failed with an ``error`` or ``internal_error`` outcome.
"""


@dataclasses.dataclass
class ControlRunner:
    """Executes all controls from a registry in topological order."""

    registry: ControlRegistry
    results: dict[tuple[str, str], RunResult] = dataclasses.field(
        default_factory=dict, init=False
    )

    def run(self) -> None:
        """Execute every registered control in dependency order.

        Controls whose dependencies produced ``error`` or
        ``internal_error`` failures are skipped and recorded as
        ``False``.
        """
        self.results.clear()

        graph: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for controller in self.registry.controllers.values():
            graph[controller.key] = list(controller.depends_on)

        order = topological_sort(graph)

        for key in order:
            ctrl = self.registry.controllers.get(key)
            if ctrl is None:
                continue

            blocked = _any_dep_failed(graph.get(key, []), self.results)
            if blocked:
                self.results[key] = False
                continue

            try:
                failures = ctrl.get_failures()
            except Exception:
                from whealth.base import Failure as F

                failures = [F(key="_internal", outcome="internal_error")]

            self.results[key] = failures


def _any_dep_failed(
    dep_keys: list[tuple[str, str]],
    results: dict[tuple[str, str], RunResult],
) -> bool:
    """Return ``True`` if any dependency has an error or internal_error."""
    for dep_key in dep_keys:
        dep_result = results.get(dep_key)
        if dep_result is False:
            return True
        if isinstance(dep_result, list):
            for f in dep_result:
                if f.outcome in ("error", "internal_error"):
                    return True
    return False
