"""Procrastinate integration for whealth health-check crons."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import timedelta
from functools import wraps
from typing import TYPE_CHECKING, Any

from django.db import close_old_connections, reset_queries

from whealth.auto_sentry import task_trace
from whealth.cron import CrontabSchedule, get_checkin_manager

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class ProcrastinateCron:
    """Cron configuration for :func:`procrastinate_task`.

    Parameters
    ----------
    expression
        Crontab expression (e.g. ``"*/5 * * * *"``).
    timezone
        IANA timezone for this schedule.
    checkin_margin
        Maximum delay before a check-in is missed.
    max_runtime
        Maximum expected runtime before overdue.
    failure_issue_threshold
        Missed check-ins before triggering a failure.
    recovery_threshold
        Successful check-ins to recover.
    """

    expression: str
    timezone: str = "UTC"
    checkin_margin: timedelta = timedelta(minutes=5)
    max_runtime: timedelta = timedelta(minutes=10)
    failure_issue_threshold: int = 2
    recovery_threshold: int = 1


def plug_psycopg_leak(func: Callable[..., Any]) -> Callable[..., Any]:
    """Close old DB connections before and after a task runs."""

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        close_old_connections()
        reset_queries()
        try:
            return func(*args, **kwargs)
        finally:
            close_old_connections()
            reset_queries()

    return wrapper


def procrastinate_task(
    app: Any,
    cron: ProcrastinateCron | None = None,
    **task_kwargs: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorate a function as a procrastinate task with health-check lifecycle.

    When ``cron`` is provided the task is also registered as periodic and
    every execution is wrapped in a ``check_in`` / ``check_out`` pair that
    persists a :class:`~whealth.models.CheckIn` record and notifies Sentry.
    Sync and async functions are both supported.

    Without ``cron`` this is a plain proxy to ``app.task()`` — no monitoring.

    Examples
    --------
    **Sync periodic task (health-checked):**

    >>> from whealth import procrastinate_task
    >>> from whealth.procrastinate import ProcrastinateCron
    >>> from procrastinate.contrib.django import procrastinate_app as app

    >>> @procrastinate_task(
    ...     app=app,
    ...     cron=ProcrastinateCron(expression="*/5 * * * *"),
    ...     queue="default",
    ... )
    ... def sync_check(timestamp: int) -> None:
    ...     _do_work()

    **Async periodic task (health-checked):**

    >>> @procrastinate_task(
    ...     app=app,
    ...     cron=ProcrastinateCron(expression="0 * * * *", timezone="US/Eastern"),
    ...     queue="default",
    ... )
    ... async def async_check(timestamp: int) -> None:
    ...     await _do_async_work()

    **One-shot task (no monitoring):**

    >>> @procrastinate_task(app=app, queue="default")
    ... def send_email(user_id: int) -> None:
    ...     _send(user_id)

    Parameters
    ----------
    app
        Procrastinate app instance (typically
        ``procrastinate.contrib.django.procrastinate_app``).
    cron
        Optional cron configuration. When set the task is registered as
        periodic and each run goes through the Sentry check-in lifecycle.
    **task_kwargs
        Extra keyword arguments forwarded to ``app.task()``
        (e.g. ``queue``, ``name``).
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if cron is None:
            return app.task(**task_kwargs)(func)  # type: ignore[no-any-return]

        is_async = inspect.iscoroutinefunction(func)

        if is_async:

            @wraps(func)
            @task_trace(name=func.__name__)
            async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
                close_old_connections()
                reset_queries()
                try:
                    receipt = get_checkin_manager().check_in(
                        slug=slug,
                        schedule=CrontabSchedule(expression=cron.expression),
                        timezone=cron.timezone,
                        checkin_margin=cron.checkin_margin,
                        max_runtime=cron.max_runtime,
                        failure_issue_threshold=cron.failure_issue_threshold,
                        recovery_threshold=cron.recovery_threshold,
                    )
                    failed = False
                    try:
                        return await func(*args, **kwargs)
                    except Exception:
                        failed = True
                        raise
                    finally:
                        get_checkin_manager().check_out(receipt, failed=failed)
                finally:
                    close_old_connections()
                    reset_queries()

            wrapper: Callable[..., Any] = async_wrapper

        else:

            @wraps(func)
            @task_trace(name=func.__name__)
            def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
                close_old_connections()
                reset_queries()
                try:
                    receipt = get_checkin_manager().check_in(
                        slug=slug,
                        schedule=CrontabSchedule(expression=cron.expression),
                        timezone=cron.timezone,
                        checkin_margin=cron.checkin_margin,
                        max_runtime=cron.max_runtime,
                        failure_issue_threshold=cron.failure_issue_threshold,
                        recovery_threshold=cron.recovery_threshold,
                    )
                    failed = False
                    try:
                        return func(*args, **kwargs)
                    except Exception:
                        failed = True
                        raise
                    finally:
                        get_checkin_manager().check_out(receipt, failed=failed)
                finally:
                    close_old_connections()
                    reset_queries()

            wrapper = sync_wrapper

        task = app.task(**task_kwargs)(wrapper)
        slug = task.name
        app.periodic(cron=cron.expression)(task)
        return task  # type: ignore[no-any-return]

    return decorator
