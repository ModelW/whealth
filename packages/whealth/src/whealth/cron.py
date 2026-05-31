"""Cron scheduling for periodic health checks."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from queue import Queue, ShutDown
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime, timedelta

from django.db import close_old_connections
from django.utils.timezone import now as django_now

from whealth.auto_sentry import capture_checkin, capture_exception


@dataclass(frozen=True)
class CrontabSchedule:
    """A crontab expression."""

    expression: str


@dataclass(frozen=True)
class CheckInStart:
    """Signals the start of a cron check-in."""

    checkin_id: uuid.UUID
    slug: str
    schedule: CrontabSchedule
    timezone: str
    checkin_margin: timedelta
    max_runtime: timedelta
    failure_issue_threshold: int
    recovery_threshold: int
    started_at: datetime


@dataclass(frozen=True)
class CheckInEnd:
    """Signals the end of a cron check-in."""

    checkin_id: uuid.UUID
    stopped_at: datetime
    failed: bool


CheckInEvent = CheckInStart | CheckInEnd


@dataclass(frozen=True)
class CheckedIn:
    """Receipt returned by :meth:`CheckinManager.check_in`.

    Pass to :meth:`CheckinManager.check_out` to finalize.
    """

    checkin_id: uuid.UUID
    slug: str
    sentry_id: str


@dataclass
class CheckinManager:
    """Manages cron check-in events on a background daemon thread."""

    queue: Queue[CheckInEvent] = field(default_factory=Queue, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    def _run(self) -> None:
        try:
            while event := self.queue.get():
                try:
                    self._process(event)
                except Exception:
                    capture_exception()
                finally:
                    self.queue.task_done()
        except ShutDown:
            pass

    def _process(self, event: CheckInEvent) -> None:
        from whealth.models import CheckIn, Cron

        try:
            match event:
                case CheckInStart():
                    cron, _ = Cron.objects.get_or_create(
                        slug=event.slug,
                        defaults={
                            "schedule_type": Cron.ScheduleType.CRONTAB,
                            "schedule": event.schedule.expression,
                            "timezone": event.timezone,
                            "checkin_margin": event.checkin_margin,
                            "max_runtime": event.max_runtime,
                            "failure_issue_threshold": event.failure_issue_threshold,
                            "recovery_threshold": event.recovery_threshold,
                        },
                    )
                    CheckIn.objects.create(
                        id=event.checkin_id,
                        cron=cron,
                        start=event.started_at,
                    )
                case CheckInEnd():
                    checkin = CheckIn.objects.get(id=event.checkin_id)
                    checkin.end = event.stopped_at
                    checkin.state = (
                        CheckIn.State.FAILED if event.failed else CheckIn.State.FINISHED
                    )
                    checkin.save(update_fields=("end", "state"))
        finally:
            close_old_connections()

    # ------------------------------------------------------------------
    # Public API  —  called from the **caller's** thread
    # ------------------------------------------------------------------

    def check_in(
        self,
        slug: str,
        schedule: CrontabSchedule,
        timezone: str,
        checkin_margin: timedelta,
        max_runtime: timedelta,
        failure_issue_threshold: int,
        recovery_threshold: int,
    ) -> CheckedIn:
        """Record the start of a check-in in the DB and in Sentry.

        Returns a :class:`CheckedIn` receipt that must be passed to
        :meth:`check_out`.
        """
        checkin_id = uuid.uuid4()
        now = django_now()

        sentry_id = capture_checkin(monitor_slug=slug, status="in_progress") or ""

        self.queue.put_nowait(
            CheckInStart(
                checkin_id=checkin_id,
                slug=slug,
                schedule=schedule,
                timezone=timezone,
                checkin_margin=checkin_margin,
                max_runtime=max_runtime,
                failure_issue_threshold=failure_issue_threshold,
                recovery_threshold=recovery_threshold,
                started_at=now,
            )
        )

        return CheckedIn(checkin_id=checkin_id, slug=slug, sentry_id=sentry_id)

    def check_out(
        self,
        receipt: CheckedIn,
        *,
        failed: bool = False,
    ) -> None:
        """Finalise a check-in — update Sentry and enqueue the DB write."""
        now = django_now()
        status = "error" if failed else "ok"
        capture_checkin(
            monitor_slug=receipt.slug,
            status=status,
            check_in_id=receipt.sentry_id or None,
        )

        self.queue.put_nowait(
            CheckInEnd(
                checkin_id=receipt.checkin_id,
                stopped_at=now,
                failed=failed,
            )
        )

    def start(self) -> None:
        """Start the background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop the processing thread."""
        self.queue.shutdown()


_cm_lock = threading.Lock()
_cm: CheckinManager | None = None


def get_checkin_manager() -> CheckinManager:
    """Return the singleton ``CheckinManager``."""
    global _cm

    if _cm is None:
        with _cm_lock:
            if _cm is None:
                _cm = CheckinManager()
                _cm.start()

    return _cm


def reset_checkin_manager(cm: CheckinManager | None = None) -> None:
    """Reset the singleton ``CheckinManager`` to None or an arbitrary value."""
    global _cm

    with _cm_lock:
        if _cm:
            _cm.stop()

        _cm = cm
