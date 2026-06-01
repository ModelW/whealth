"""Cron schedule health control."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from croniter import croniter  # type: ignore[import-untyped]
from django.utils.timezone import now as django_now
from whealth import BaseControl, Failure

if TYPE_CHECKING:
    from whealth.models import CheckIn, Cron


_BATCH = 10
"""Number of schedule slots to examine per batch."""


@dataclass(frozen=True)
class Slot:
    """A single scheduled execution slot."""

    scheduled_at: datetime
    """When the cron *should* have fired (UTC)."""
    covered_by: CheckIn | None = None
    """The check-in that covered this slot, or ``None`` if missed."""


def _scheduled_slots(
    cron: Cron,
    *,
    before: datetime,
    count: int,
) -> list[datetime]:
    """Return the last ``count`` scheduled times for *cron* before *before*.

    Uses ``croniter`` to walk from the cron expression backward from *before*.
    """
    it = croniter(cron.schedule, before, ret_type=datetime)
    return [it.get_prev(datetime) for _ in range(count)]


def _slots_with_checkins(cron: Cron, slots: list[datetime]) -> list[Slot]:
    """Annotate each scheduled slot with its covering check-in (if any).

    A check-in covers a slot when its ``start`` is within ``checkin_margin``
    **before** the scheduled time, or within ``max_runtime`` **after** it.
    """
    if not slots:
        return []

    margin = cron.checkin_margin
    runtime = cron.max_runtime

    window_start = slots[-1] - margin
    window_end = slots[0] + runtime

    from whealth.models import CheckIn

    checkins = list(
        CheckIn.objects.filter(
            cron=cron,
            start__gte=window_start,
            start__lte=window_end,
        ).order_by("start")
    )

    result: list[Slot] = []
    for scheduled_at in slots:
        matching = [
            c
            for c in checkins
            if scheduled_at - margin <= c.start <= scheduled_at + runtime
        ]
        result.append(
            Slot(
                scheduled_at=scheduled_at,
                covered_by=max(matching, key=lambda x: x.start) if matching else None,
            ),
        )

    return result


def _evaluate_cron(cron: Cron) -> Failure | None:
    """Walk scheduled slots forward (nearest to farthest) to assess health.

    Counts consecutive misses starting from the most recent slot.  A
    successful check-in resets the counter to 0 and *stops the search* —
    if the latest execution was fine the cron is healthy regardless of older
    failures.

    When the miss counter reaches ``failure_issue_threshold`` a
    ``Failure`` is returned.

    Returns ``None`` when the cron is healthy.
    """
    now = django_now()
    cursor = now
    consecutive_misses = 0

    while True:
        slots = _scheduled_slots(cron, before=cursor, count=_BATCH)

        if not slots:
            return (
                None
                if consecutive_misses < cron.failure_issue_threshold
                else Failure(
                    key=cron.slug,
                    outcome="error",
                    context={
                        "consecutive_misses": consecutive_misses,
                        "threshold": cron.failure_issue_threshold,
                        "schedule": cron.schedule,
                    },
                )
            )

        annotated = _slots_with_checkins(cron, slots)

        # Walk newest → oldest.
        for slot in annotated:
            if slot.covered_by is not None and slot.covered_by.state == "finished":
                consecutive_misses = 0
                return None  # healthy — recent hit proves it

            if (
                slot.covered_by is not None
                and slot.covered_by.state == "started"
                and now < slot.covered_by.start + cron.max_runtime
            ):
                return None  # still in progress within max_runtime — clemency

            consecutive_misses += 1

            if consecutive_misses >= cron.failure_issue_threshold:
                return Failure(
                    key=cron.slug,
                    outcome="error",
                    context={
                        "consecutive_misses": consecutive_misses,
                        "threshold": cron.failure_issue_threshold,
                        "schedule": cron.schedule,
                    },
                )

        # Advance cursor before the oldest slot in this batch and continue.
        cursor = slots[-1]

        if cursor < now - timedelta(days=7):
            return None


class Control(BaseControl):
    """Check that every registered cron is running on schedule.

    For each :class:`~whealth.models.Cron` the control walks backward through
    the cron's scheduled slots using ``croniter``, checks whether a matching
    :class:`~whealth.models.CheckIn` exists for each slot, and reports a
    failure when the number of consecutive missed slots reaches the cron's
    ``failure_issue_threshold``.
    """

    def get_failures(self) -> list[Failure]:
        """Check each cron for missed or overdue check-ins."""
        from whealth.models import Cron

        failures: list[Failure] = []
        for cron in Cron.objects.iterator():
            failure = _evaluate_cron(cron)
            if failure is not None:
                failures.append(failure)
        return failures
