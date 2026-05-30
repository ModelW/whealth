"""Runner that executes all registered controls."""

from __future__ import annotations

import dataclasses
import logging
from typing import TYPE_CHECKING, Literal

from django.db import transaction
from django.utils.timezone import now as django_now

from whealth.auto_sentry import capture_exception
from whealth.graph import topological_sort

if TYPE_CHECKING:
    from whealth.base import Failure
    from whealth.registry import ControlRegistry

logger = logging.getLogger("whealth.runner")


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
            except Exception as exc:
                capture_exception(exc)
                from whealth.base import Failure as F

                failures = [F(key="_internal", outcome="internal_error")]

            self.results[key] = failures

    def run_and_sync(self) -> None:
        """Run all controls and sync results into the database.

        Calls :meth:`run` and then :meth:`sync_incidents` to create and
        close :class:`~whealth.models.Incident` rows for each control
        failure.  If the sync fails (e.g. database unavailable) the
        error is captured via Sentry and logged — the in-memory results
        are preserved.
        """
        self.run()
        self.sync_incidents()

    def sync_incidents(self) -> None:
        """Create incidents for new failures and close resolved ones.

        For each controller key with a ``list[Failure]`` result:
        - Open incidents whose ``(control, key)`` no longer appear in
          the failures are closed (``date_end`` set to now).
        - New failures not yet covered by an open incident get a new
          incident record created.

        Controls that were blocked (``False`` result) or not present
        in the results are ignored — incidents stay open.
        """
        try:
            self._sync_incidents()
        except Exception as exc:
            capture_exception(exc)
            logger.exception("Failed to sync incidents to the database.")

    def _sync_incidents(self) -> None:
        """Inner implementation of incident sync."""
        from whealth.models import Incident

        now = django_now()
        failure_map = _build_failure_map(self.results, self.registry)
        pks = list(failure_map.keys())

        open_incidents: dict[tuple[int, str], Incident] = {}
        for inc in Incident.objects.filter(
            control_id__in=pks,
            date_end__isnull=True,
        ):
            cid = inc.control_id  # type: ignore[attr-defined]
            open_incidents[(cid, inc.key)] = inc

        to_create: list[Incident] = []
        to_close: list[Incident] = []

        for pk, fkeys in failure_map.items():
            for fkey in fkeys:
                inc_key = (pk, fkey)
                if inc_key not in open_incidents:
                    to_create.append(Incident(control_id=pk, key=fkey, date_start=now))
                else:
                    del open_incidents[inc_key]

        to_close = list(open_incidents.values())

        with transaction.atomic():
            if to_create:
                Incident.objects.bulk_create(to_create)
            if to_close:
                Incident.objects.filter(pk__in={i.pk for i in to_close}).update(
                    date_end=now
                )


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


def _build_failure_map(
    results: dict[tuple[str, str], RunResult],
    registry: ControlRegistry,
) -> dict[int, set[str]]:
    """Map control PKs to the set of failure keys from *results*."""
    from whealth.models import Control as ControlModel

    controller_keys: set[tuple[str, str]] = set()
    for controller in registry.controllers.values():
        controller_keys.add(controller.key)

    pk_map: dict[tuple[str, str], int] = {}
    for row in ControlModel.objects.filter(active=True).values(
        "pk", "slug", "app_label"
    ):
        pk_map[(row["app_label"], row["slug"])] = row["pk"]

    failure_map: dict[int, set[str]] = {}
    for key, result in results.items():
        if not isinstance(result, list):
            continue
        pk = pk_map.get(key)
        if pk is None:
            continue
        fkeys: set[str] = set()
        for failure in result:
            fkeys.add(failure.key)
        failure_map[pk] = fkeys
    return failure_map
