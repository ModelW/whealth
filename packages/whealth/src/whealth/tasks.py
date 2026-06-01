"""Procrastinate tasks for whealth controls.

This module declares itself only when ``procrastinate`` is importable.
Projects that opt in via the ``[procrastinate]`` extra get a periodic cron
that runs all active controls every minute.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.utils.timezone import now as django_now

logger = logging.getLogger("whealth.tasks")
try:
    from procrastinate.contrib.django import app
except ImportError:
    app = None  # type: ignore[assignment]


if app is not None:
    from whealth.procrastinate import ProcrastinateCron, procrastinate_task
    from whealth.registry import get_control_registry

    @procrastinate_task(
        app=app,
        cron=ProcrastinateCron(expression="* * * * *"),
        queue="health",
    )
    def run_controls(timestamp: int) -> None:
        """Run all registered controls and sync incidents."""
        registry = get_control_registry()
        registry.sync_to_db()

        runner = registry.get_runner()
        runner.run_and_sync()

    @procrastinate_task(
        app=app,
        cron=ProcrastinateCron(expression="0 3 * * *"),
        queue="maintenance",
    )
    def prune_run_logs(timestamp: int) -> None:
        """Delete ``RunRecord`` rows older than the configured retention period.

        The retention is read from Django setting
        ``WHEALTH_RUN_LOG_RETENTION``.  Accepted values:

        * a :class:`~datetime.timedelta` — used directly.
        * a ``dict`` — unpacked as kwargs to ``timedelta(**value)``.
        * an ``int`` — treated as a number of days.
        * ``None`` or absent — defaults to 365 days.
        """
        from whealth.models import RunRecord

        retention = _resolve_run_log_retention()
        cutoff = django_now() - retention
        deleted, _ = RunRecord.objects.filter(date_start__lt=cutoff).delete()
        if deleted:
            logger.info("Pruned %d run record(s) older than %s", deleted, cutoff)


def _resolve_run_log_retention() -> timedelta:
    """Resolve ``WHEALTH_RUN_LOG_RETENTION`` from Django settings.

    Return value
    ------------
    :class:`~datetime.timedelta`
        The retention period to use (defaults to 365 days).
    """
    raw: Any = getattr(settings, "WHEALTH_RUN_LOG_RETENTION", None)

    if raw is None:
        return timedelta(days=365)

    if isinstance(raw, timedelta):
        return raw

    if isinstance(raw, dict):
        return timedelta(**raw)

    if isinstance(raw, int):
        return timedelta(days=raw)

    msg = (
        f"WHEALTH_RUN_LOG_RETENTION must be a timedelta, a dict of "
        f"timedelta kwargs, or an int (days); got {type(raw).__name__}"
    )
    raise TypeError(msg)
