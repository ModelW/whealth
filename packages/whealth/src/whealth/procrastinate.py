"""Procrastinate integration for whealth health-check crons.

The integration is built on Procrastinate's middleware mechanism
(Procrastinate >= 3.9):

* :func:`checkin_sync_middleware` / :func:`checkin_async_middleware` —
  worker-wide *task middleware* implementing the cron check-in
  lifecycle (DB record + Sentry cron monitor) for every task declared
  with a cron through :func:`procrastinate_task`.
* :func:`sentry_worker_middleware` — *worker middleware* wrapping every
  job in a Sentry isolation scope and transaction.

With Django, all of them are installed automatically by whealth's
``AppConfig.ready()`` — no setup needed on the user's part.  Outside
Django (or on a hand-built app), call :func:`install_middleware`
yourself, or pass the middleware directly to ``app.run_worker()``.

The :func:`procrastinate_task` decorator is kept as the public entry
point for declaring health-checked periodic tasks.  When the worker-wide
middleware is not installed, the decorator's own per-task middleware
performs the check-ins, so existing applications keep working without
any worker configuration.  When both are present, the per-task
middleware detects the worker-wide one and stands down — check-ins are
never doubled.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import timedelta
from functools import wraps
from typing import TYPE_CHECKING, Any

from django.db import close_old_connections, reset_queries

from whealth.auto_sentry import capture_exception, isolation_scope, start_transaction
from whealth.cron import CrontabSchedule, get_checkin_manager

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from procrastinate import job_context, worker


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
    """Close old DB connections before and after a task runs.

    .. deprecated::
        Procrastinate's Django integration (>= 3.9) performs this cleanup
        itself through task middleware — this wrapper is kept only for
        backwards compatibility with existing applications.
    """

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


# ---------------------------------------------------------------------------
# Check-in lifecycle (task middleware)
# ---------------------------------------------------------------------------

_cron_configs: dict[str, ProcrastinateCron] = {}
"""Cron configuration per task name, populated by :func:`procrastinate_task`."""


def get_cron_config(task_name: str) -> ProcrastinateCron | None:
    """Return the cron configuration declared for a task, if any."""
    return _cron_configs.get(task_name)


def _check_in(cron: ProcrastinateCron, slug: str) -> Any:
    """Open a check-in for the given cron/slug pair."""
    return get_checkin_manager().check_in(
        slug=slug,
        schedule=CrontabSchedule(expression=cron.expression),
        timezone=cron.timezone,
        checkin_margin=cron.checkin_margin,
        max_runtime=cron.max_runtime,
        failure_issue_threshold=cron.failure_issue_threshold,
        recovery_threshold=cron.recovery_threshold,
    )


def checkin_sync_middleware(
    call_next: Callable[[], Any],
    context: job_context.JobContext,
    worker: worker.Worker,
) -> Any:
    """Sync task middleware implementing the check-in lifecycle.

    Wraps every *sync* task declared with a cron through
    :func:`procrastinate_task` in a ``check_in`` / ``check_out`` pair
    that persists a :class:`~whealth.models.CheckIn` record and notifies
    the Sentry cron monitor.  Tasks without a cron pass through
    untouched.

    Install worker-wide together with :func:`checkin_async_middleware`
    (task middleware is kind-filtered per task, so each task gets
    exactly the matching one).
    """
    cron = get_cron_config(context.task.name)
    if cron is None:
        return call_next()

    receipt = _check_in(cron, context.task.name)
    failed = False
    try:
        return call_next()
    except Exception:
        failed = True
        raise
    finally:
        get_checkin_manager().check_out(receipt, failed=failed)


async def checkin_async_middleware(
    call_next: Callable[[], Awaitable[Any]],
    context: job_context.JobContext,
    worker: worker.Worker,
) -> Any:
    """Async task middleware implementing the check-in lifecycle.

    Async counterpart of :func:`checkin_sync_middleware`, wrapping
    *async* cron tasks.
    """
    cron = get_cron_config(context.task.name)
    if cron is None:
        return await call_next()

    receipt = _check_in(cron, context.task.name)
    failed = False
    try:
        return await call_next()
    except Exception:
        failed = True
        raise
    finally:
        get_checkin_manager().check_out(receipt, failed=failed)


_CHECKIN_MIDDLEWARES = (checkin_sync_middleware, checkin_async_middleware)


def _worker_handles_checkins(worker: worker.Worker | None) -> bool:
    """Whether the running worker already has the check-in middleware."""
    if worker is None:
        return False
    return any(mw in _CHECKIN_MIDDLEWARES for mw in worker.task_middleware)


def _fallback_checkin_sync(
    call_next: Callable[[], Any],
    context: job_context.JobContext,
    worker: worker.Worker,
) -> Any:
    """Per-task fallback attached by :func:`procrastinate_task` (sync).

    Performs the check-in lifecycle only when the worker does *not*
    already run :func:`checkin_sync_middleware` worker-wide, so
    check-ins are never doubled.
    """
    if _worker_handles_checkins(worker):
        return call_next()
    return checkin_sync_middleware(call_next, context, worker)


async def _fallback_checkin_async(
    call_next: Callable[[], Awaitable[Any]],
    context: job_context.JobContext,
    worker: worker.Worker,
) -> Any:
    """Per-task fallback attached by :func:`procrastinate_task` (async).

    Async counterpart of :func:`_fallback_checkin_sync`.
    """
    if _worker_handles_checkins(worker):
        return await call_next()
    return await checkin_async_middleware(call_next, context, worker)


# ---------------------------------------------------------------------------
# Sentry tracing (worker middleware)
# ---------------------------------------------------------------------------


async def sentry_worker_middleware(
    call_next: Callable[[], Awaitable[Any]],
    context: job_context.JobContext,
    worker: worker.Worker,
) -> Any:
    """Wrap every job in a Sentry isolation scope and transaction.

    Worker middleware runs on the event loop for both sync and async
    tasks, so a single middleware covers the whole worker.  Each job gets:

    * its own isolation scope, so tags/breadcrumbs don't bleed between
      jobs;
    * a transaction (``queue.task.procrastinate``) carrying queue
      metadata, so spans opened inside the task attach to it;
    * exception capture — the exception is reported to Sentry and then
      re-raised so Procrastinate's retry/failure logic is unaffected.

    Install it worker-wide::

        PROCRASTINATE_WORKER_DEFAULTS = {
            "worker_middleware": [sentry_worker_middleware],
        }

    All Sentry calls degrade to no-ops when ``sentry_sdk`` is missing.
    """
    from procrastinate import exceptions as procrastinate_exceptions

    job = context.job

    with (
        isolation_scope(),
        start_transaction(
            op="queue.task.procrastinate",
            name=context.task.name,
        ) as transaction,
    ):
        transaction.set_data("messaging.destination.name", job.queue)
        if job.id is not None:
            transaction.set_data("messaging.message.id", job.id)
        transaction.set_data("messaging.message.retry.count", job.attempts)

        try:
            return await call_next()
        except (
            procrastinate_exceptions.JobAborted,
            procrastinate_exceptions.JobRetry,
        ):
            # Deliberate lifecycle signals, not application errors.
            raise
        except Exception as exc:
            capture_exception(exc)
            raise


# ---------------------------------------------------------------------------
# Worker-wide installation
# ---------------------------------------------------------------------------


def install_middleware(app: Any) -> None:
    """Install whealth's middleware worker-wide on a Procrastinate app.

    Adds the check-in task middleware (sync + async) and the Sentry
    worker middleware to the app's ``worker_defaults`` — idempotent, so
    calling it twice doesn't stack middleware.

    With Django this is called automatically by whealth's
    ``AppConfig.ready()`` — no setup needed.  Outside Django, call it on
    your app before running the worker.
    """
    defaults = app.worker_defaults

    task_mw = list(defaults.get("task_middleware") or [])
    for mw in _CHECKIN_MIDDLEWARES:
        if mw not in task_mw:
            task_mw.append(mw)
    defaults["task_middleware"] = task_mw

    worker_mw = list(defaults.get("worker_middleware") or [])
    if sentry_worker_middleware not in worker_mw:
        worker_mw.append(sentry_worker_middleware)
    defaults["worker_middleware"] = worker_mw


chained_on_app_ready: Any = None
"""User-configured ``PROCRASTINATE_ON_APP_READY`` hook to chain, if any.

Set by :meth:`whealth.apps.WhealthConfig.ready` when it takes over the
setting while the user had configured their own hook.
"""


def on_app_ready(app: Any) -> None:
    """``PROCRASTINATE_ON_APP_READY`` hook installing whealth's middleware.

    Wired automatically by :meth:`whealth.apps.WhealthConfig.ready` when
    procrastinate's Django app initializes after whealth's.  If the user
    had configured their own hook, it is called first.
    """
    from django.utils.module_loading import import_string

    if chained_on_app_ready:
        hook = (
            import_string(chained_on_app_ready)
            if isinstance(chained_on_app_ready, str)
            else chained_on_app_ready
        )
        hook(app)

    install_middleware(app)


# ---------------------------------------------------------------------------
# Task declaration
# ---------------------------------------------------------------------------


def procrastinate_task(
    app: Any = None,
    cron: ProcrastinateCron | None = None,
    **task_kwargs: Any,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Declare a procrastinate task with health-check lifecycle.

    When ``cron`` is provided the task is registered as periodic and
    every execution is wrapped in a ``check_in`` / ``check_out`` pair
    that persists a :class:`~whealth.models.CheckIn` record and notifies
    Sentry.  Sync and async functions are both supported.

    The check-in is performed by the worker-wide middleware when
    installed (see :func:`install_middleware`), or by a per-task
    fallback middleware otherwise — never both.

    Without ``cron`` this is a plain proxy to ``app.task()`` — no
    monitoring.

    For distributed tracing of task executions, also install
    :func:`sentry_worker_middleware` on the worker (done automatically
    by :func:`install_middleware`).

    Examples
    --------
    **Sync periodic task (health-checked):**

    >>> from whealth import procrastinate_task
    >>> from whealth.procrastinate import ProcrastinateCron

    >>> @procrastinate_task(
    ...     cron=ProcrastinateCron(expression="*/5 * * * *"),
    ...     queue="default",
    ... )
    ... def sync_check(timestamp: int) -> None:
    ...     _do_work()

    **Async periodic task (health-checked):**

    >>> @procrastinate_task(
    ...     cron=ProcrastinateCron(expression="0 * * * *", timezone="US/Eastern"),
    ...     queue="default",
    ... )
    ... async def async_check(timestamp: int) -> None:
    ...     await _do_async_work()

    **One-shot task (no monitoring):**

    >>> @procrastinate_task(queue="default")
    ... def send_email(user_id: int) -> None:
    ...     _send(user_id)

    Parameters
    ----------
    app
        Procrastinate app instance.  Defaults to the Django-managed app
        (``procrastinate.contrib.django.app``), which is the right thing
        in a Django project — only pass an app explicitly for a
        hand-built (non-Django) Procrastinate app.
    cron
        Optional cron configuration. When set the task is registered as
        periodic and each run goes through the Sentry check-in lifecycle.
    **task_kwargs
        Extra keyword arguments forwarded to ``app.task()``
        (e.g. ``queue``, ``name``).
    """
    if app is None:
        # Deferred import: whealth must stay importable without Django's
        # procrastinate contrib.  The contrib `app` is a proxy that is
        # safe to import at any time — task registration through it is
        # buffered until the Django app is ready.
        from procrastinate.contrib.django import app as django_app

        app = django_app

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        if cron is None:
            return app.task(**task_kwargs)(func)  # type: ignore[no-any-return]

        fallback = (
            _fallback_checkin_async
            if inspect.iscoroutinefunction(func)
            else _fallback_checkin_sync
        )
        existing = list(task_kwargs.pop("task_middleware", None) or [])

        task = app.task(
            task_middleware=[fallback, *existing],
            **task_kwargs,
        )(func)
        _cron_configs[task.name] = cron
        app.periodic(cron=cron.expression)(task)
        return task  # type: ignore[no-any-return]

    return decorator
