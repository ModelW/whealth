"""Runner that executes all registered controls."""

from __future__ import annotations

import dataclasses
import logging
import socket
import sys
from typing import TYPE_CHECKING, Any, Literal

from django.db import transaction
from django.utils.timezone import now as django_now

from whealth.auto_sentry import capture_exception
from whealth.graph import topological_sort

if TYPE_CHECKING:
    from datetime import datetime

    from whealth.base import Failure
    from whealth.models import Incident
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
    _run_started: datetime | None = dataclasses.field(default=None, init=False)

    def run(self) -> None:
        """Execute every registered control in dependency order.

        Controls whose dependencies produced ``error`` or
        ``internal_error`` failures are skipped and recorded as
        ``False``.  Failures whose corresponding incidents have been
        ignored in the database are *not* treated as blocking —
        provided the database is reachable.
        """
        self.results.clear()
        self._run_started = django_now()

        ignored_keys = _get_ignored_incident_keys() or set()

        graph: dict[tuple[str, str], list[tuple[str, str]]] = {}
        for controller in self.registry.controllers.values():
            graph[controller.key] = list(controller.depends_on)

        order = topological_sort(graph)

        for key in order:
            ctrl = self.registry.controllers.get(key)
            if ctrl is None:
                continue

            blocked = _any_dep_failed(graph.get(key, []), self.results, ignored_keys)
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
        from whealth.models import Incident, RunRecord

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

        to_create, to_update_context = _diff_incidents(failure_map, open_incidents, now)
        to_close = list(open_incidents.values())

        results_serialised: dict[str, Any] = {}
        for key, result in self.results.items():
            label = f"{key[0]}.{key[1]}"
            if result is False:
                results_serialised[label] = None
            else:
                results_serialised[label] = [dataclasses.asdict(f) for f in result]

        run_start = self._run_started or now
        run_duration = now - run_start if self._run_started else None

        with transaction.atomic():
            if to_create:
                Incident.objects.bulk_create(to_create)
            if to_close:
                Incident.objects.filter(pk__in={i.pk for i in to_close}).update(
                    date_end=now
                )
            if to_update_context:
                Incident.objects.bulk_update(to_update_context, ["context"])
            RunRecord.objects.create(
                date_start=run_start,
                hostname=socket.gethostname(),
                cli=" ".join(sys.argv),
                duration=run_duration,
                results=results_serialised,
            )


# ---------------------------------------------------------------------------
# Dependency-comparison helpers
# ---------------------------------------------------------------------------


def _diff_incidents(
    failure_map: dict[int, dict[str, Any]],
    open_incidents: dict[tuple[int, str], Incident],
    now: Any,
) -> tuple[list[Incident], list[Incident]]:
    """Diff current failures against open incidents.

    Returns a tuple of ``(to_create, to_update_context)``.  Incidents
    whose keys match are popped from *open_incidents* so that whatever
    remains can be closed.
    """
    from whealth.models import Incident

    to_create: list[Incident] = []
    to_update_context: list[Incident] = []

    for pk, finfos in failure_map.items():
        for fkey, fctx in finfos.items():
            inc_key = (pk, fkey)
            safe_ctx = fctx if fctx is not None else {}
            if inc_key not in open_incidents:
                to_create.append(
                    Incident(
                        control_id=pk,
                        key=fkey,
                        date_start=now,
                        context=safe_ctx,
                    )
                )
            else:
                existing = open_incidents[inc_key]
                if existing.context != safe_ctx:
                    existing.context = safe_ctx
                    to_update_context.append(existing)
                del open_incidents[inc_key]

    return to_create, to_update_context


def _get_ignored_incident_keys() -> set[tuple[tuple[str, str], str]] | None:
    """Return the set of ``(control_key, failure_key)`` for ignored incidents.

    Returns the set of ``(control_key, failure_key)`` for incidents that
    are currently ignored (``date_ignored IS NOT NULL`` and still open).
    Returns ``None`` if the database is unreachable, in which case the
    runner falls back to strict blocking.
    """
    from whealth.models import Incident

    try:
        ignored: set[tuple[tuple[str, str], str]] = set()
        for inc in (
            Incident.objects.filter(
                date_end__isnull=True,
                date_ignored__isnull=False,
            )
            .select_related("control")
            .iterator()
        ):
            ignored.add(((inc.control.app_label, inc.control.slug), inc.key))
        return ignored
    except Exception:
        logger.exception("Failed to fetch ignored incidents; using strict blocking.")
        return None


def _any_dep_failed(
    dep_keys: list[tuple[str, str]],
    results: dict[tuple[str, str], RunResult],
    ignored_keys: set[tuple[tuple[str, str], str]] | None = None,
) -> bool:
    """Return ``True`` if any dependency has an error or internal_error.

    Failures whose incidents have been ignored in the database are
    skipped, so an ignored dep cannot block its dependents.
    """
    for dep_key in dep_keys:
        dep_result = results.get(dep_key)
        if dep_result is False:
            return True
        if isinstance(dep_result, list):
            for f in dep_result:
                if f.outcome not in ("error", "internal_error"):
                    continue
                if ignored_keys is not None and (dep_key, f.key) in ignored_keys:
                    continue
                return True
    return False


def _build_failure_map(
    results: dict[tuple[str, str], RunResult],
    registry: ControlRegistry,
) -> dict[int, dict[str, Any]]:
    """Map control PKs to ``{failure_key: context}`` from *results*."""
    from whealth.models import Control as ControlModel

    controller_keys: set[tuple[str, str]] = set()
    for controller in registry.controllers.values():
        controller_keys.add(controller.key)

    pk_map: dict[tuple[str, str], int] = {}
    for row in ControlModel.objects.filter(active=True).values(
        "pk", "slug", "app_label"
    ):
        pk_map[(row["app_label"], row["slug"])] = row["pk"]

    failure_map: dict[int, dict[str, Any]] = {}
    for key, result in results.items():
        if not isinstance(result, list):
            continue
        pk = pk_map.get(key)
        if pk is None:
            continue
        fmap: dict[str, Any] = {}
        for failure in result:
            fmap[failure.key] = failure.context
        failure_map[pk] = fmap
    return failure_map
