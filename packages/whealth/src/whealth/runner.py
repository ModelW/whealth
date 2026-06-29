"""Runner that executes all registered controls."""

from __future__ import annotations

import dataclasses
import logging
import socket
import sys
from dataclasses import asdict
from shlex import quote
from typing import TYPE_CHECKING, Any, Literal

from django.utils import timezone

from whealth.base import Failure

if TYPE_CHECKING:
    import datetime

    from whealth.registry import Controller, ControlRegistry


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
    """The registry that created us"""

    date_start: datetime.datetime | None = None
    """When this run started."""

    duration: datetime.timedelta | None = None
    """Wall-clock duration of this run."""

    hostname: str | None = None
    """Hostname of the machine that performed this run."""

    results: dict[tuple[str, str], RunResult] = dataclasses.field(
        default_factory=dict, init=False
    )
    """Cached results of the run"""

    @property
    def results_json(self) -> dict[str, Any]:
        """Shortcut to serialize results as JSON."""
        return {
            ".".join(k): [asdict(f) for f in v] if isinstance(v, list) else v
            for k, v in self.results.items()
        }

    @classmethod
    def from_results(
        cls,
        results_json: dict[str, Any],
        registry: ControlRegistry,
        *,
        date_start: datetime.datetime | None = None,
        duration: datetime.timedelta | None = None,
        hostname: str | None = None,
    ) -> ControlRunner:
        """Re-hydrate a ControlRunner instance from serialized results JSON."""
        from whealth.base import Failure

        runner = cls(
            registry=registry,
            date_start=date_start,
            duration=duration,
            hostname=hostname,
        )

        results_map: dict[tuple[str, str], RunResult] = {}
        for label, val in results_json.items():
            app_label, slug = label.split(".", 1)
            key = (app_label, slug)
            if val is False:
                results_map[key] = False
            elif isinstance(val, list):
                results_map[key] = [
                    Failure(
                        key=item["key"],
                        outcome=item["outcome"],
                        context=item.get("context"),
                    )
                    for item in val
                ]
            else:
                results_map[key] = val

        runner.results = results_map
        return runner

    def run_and_sync(self) -> None:
        """Run the full process and saves it into DB.

        There is a first built-in check to see if the database connection works
        properly. If not, we're simply failing right away, without saving
        anything (because there is nothing to save it to).
        """
        start, end = self._run()

        if self.results[("whealth", "database")] == []:
            self.registry.sync_to_db()
            self._upsert_incidents()
            self._save_run(start, end)

    def _run(self) -> tuple[datetime.datetime, datetime.datetime]:
        start = timezone.now()

        for controller in self.registry.get_sorted_controls():
            self._run_one_control(controller)

        end = timezone.now()

        return start, end

    def _run_one_control(self, controller: Controller) -> None:
        """Run one specific control.

        Taking into account the following rules:

        - To ignore it if dependencies failed
        - And to drop ignored failures if the control is ignorable
        """
        from whealth.auto_sentry import capture_exception

        try:
            failures = controller.get_failures()
        except Exception as exc:
            capture_exception(exc)
            failures = [
                Failure(
                    key=controller.slug,
                    outcome="internal_error",
                    context={"exception": str(exc)},
                )
            ]

        for dependency in controller.depends_on:
            match self.results[dependency]:
                case False:
                    self.results[controller.key] = False
                    return
                case list(dep_failures):
                    if any(
                        f.outcome in ("error", "internal_error") for f in dep_failures
                    ):
                        self.results[controller.key] = False
                        return

        if controller.is_ignorable:
            failures = self._drop_ignored(controller.key, failures)

        self.results[controller.key] = failures

    def _drop_ignored(
        self, control_id: tuple[str, str], failures: list[Failure]
    ) -> list[Failure]:
        """Drop ignored failures from a control's result.

        Incidents can be ignored through the database. In order to do that in a
        way that isn't too slow, we're filtering out potentially active
        incidents, and we check if within this we can find an ignore notice.
        """
        from .models import Incident

        ignored = set(
            Incident.objects.filter(
                control__slug=control_id[1],
                control__app_label=control_id[0],
                key__in=list(set(f.key for f in failures)),
                date_ignored__isnull=False,
            ).values_list("key", flat=True)
        )

        return [f for f in failures if f.key not in ignored]

    def _upsert_incidents(self) -> None:
        """Update the database with the latest incidents."""
        from .models import Control, Incident

        now = timezone.now()

        context_mapping, db_mapping, to_close, to_insert = self._diff_incidents()

        control_map = {
            (control.app_label, control.slug): control
            for control in Control.objects.all()
        }

        if to_insert:
            Incident.objects.bulk_create(
                [
                    Incident(
                        date_start=now,
                        control=control_map[(app_label, slug)],
                        key=key,
                        context=context_mapping[(app_label, slug, key)] or {},
                    )
                    for (app_label, slug, key) in to_insert
                ],
                ignore_conflicts=True,
            )

        if to_close:
            Incident.objects.filter(
                pk__in=list(db_mapping[k] for k in to_close)
            ).update(date_end=now)

    def _diff_incidents(
        self,
    ) -> tuple[
        dict[tuple[str, str, str], Any],
        dict[tuple[str, str, str], int],
        set[tuple[str, str, str]],
        set[tuple[str, str, str]],
    ]:
        """Compute the diff between DB and results."""
        from .models import Incident

        active_incidents = Incident.objects.filter(
            date_end__isnull=True,
            date_ignored__isnull=True,
        ).values("pk", "control__slug", "control__app_label", "key")

        db_mapping: dict[tuple[str, str, str], int] = dict()

        for row in active_incidents:
            db_mapping[
                (row["control__app_label"], row["control__slug"], row["key"])
            ] = row["pk"]

        is_in_db = set(db_mapping.keys())
        is_in_results = set()
        context_mapping: dict[tuple[str, str, str], Any] = dict()

        for (app_label, slug), failures in self.results.items():
            if not failures:
                continue

            for failure in failures:
                is_in_results.add((app_label, slug, failure.key))
                context_mapping[(app_label, slug, failure.key)] = failure.context

        to_insert = is_in_results - is_in_db
        to_close = is_in_db - is_in_results

        return context_mapping, db_mapping, to_close, to_insert

    def _save_run(self, start: datetime.datetime, end: datetime.datetime) -> None:
        from .models import RunRecord

        self.date_start = start
        self.duration = end - start
        self.hostname = socket.gethostname()

        RunRecord.objects.create(
            date_start=start,
            date_end=end,
            duration=self.duration,
            hostname=self.hostname,
            cli=" ".join(quote(arg) for arg in sys.argv),
            results=self.results_json,
        )

    def is_control_ok(self, app_label: str, slug: str) -> bool:
        """Return True if the control is considered OK (not failed)."""
        result = self.results[(app_label, slug)]

        if isinstance(result, list):
            return not any(f.outcome in ("error", "internal_error") for f in result)
        else:
            return True

    def is_control_deep_ok(self, app_label: str, slug: str) -> bool:
        """Return True if the control and all of its ancestors are OK."""
        key = (app_label, slug)
        ancestors = self.registry.get_ancestors(key)
        return all(self.is_control_ok(*ancestor) for ancestor in ancestors | {key})

    def should_restart_service(self, service: str) -> bool:
        """Check if any failed control recommends restarting the specified service."""
        from whealth import RestartRemediation

        for app_label, slug in self.results.keys():
            if self.is_control_ok(app_label, slug):
                continue

            if not (controller := self.registry.get(app_label, slug)):
                msg = f"Control {app_label}.{slug} not found in registry"
                raise KeyError(msg)

            results = self.results[(app_label, slug)]

            if not isinstance(results, list):
                continue

            for failure in results:
                match controller.get_remediation(failure):
                    case RestartRemediation(components=components):
                        if service in components:
                            return True

        return False

    def is_ok(self) -> bool:
        """Check that all controls are entirely fine."""
        return all(result == [] for result in self.results.values())
