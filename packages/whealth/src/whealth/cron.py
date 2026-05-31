"""Cron scheduling for periodic health checks."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from queue import Queue
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime, timedelta

from whealth.auto_sentry import capture_checkin, capture_exception
from whealth.models import CheckIn, Cron


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


@dataclass
class CheckinManager:
    """Manages cron check-in events on a background daemon thread."""

    queue: Queue[CheckInEvent] = field(default_factory=Queue, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    def _run(self) -> None:
        while event := self.queue.get():
            try:
                self._process(event)
            except Exception:
                capture_exception()
            finally:
                self.queue.task_done()

    def _process(self, event: CheckInEvent) -> None:
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
                sentry_id = capture_checkin(
                    monitor_slug=event.slug,
                    status="in_progress",
                )
                CheckIn.objects.create(
                    id=event.checkin_id,
                    cron=cron,
                    start=event.started_at,
                    sentry_checkin_id=sentry_id or "",
                )
            case CheckInEnd():
                checkin = CheckIn.objects.select_related("cron").get(
                    id=event.checkin_id
                )
                status = "error" if event.failed else "ok"
                duration_s = (event.stopped_at - checkin.start).total_seconds()
                capture_checkin(
                    monitor_slug=checkin.cron.slug,
                    status=status,
                    duration_s=duration_s,
                    check_in_id=checkin.sentry_checkin_id or None,
                )
                checkin.end = event.stopped_at
                checkin.state = (
                    CheckIn.State.FAILED if event.failed else CheckIn.State.FINISHED
                )
                checkin.save(update_fields=("end", "state"))

    def send(self, event: CheckInEvent) -> None:
        """Enqueue a check-in event for processing."""
        self.queue.put_nowait(event)

    def start(self) -> None:
        """Start the background daemon thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()
        self._thread = thread


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
