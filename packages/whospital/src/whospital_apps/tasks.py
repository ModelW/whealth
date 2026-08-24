"""Procrastinate tasks for health-check crons."""

from __future__ import annotations

from whealth.procrastinate import ProcrastinateCron, procrastinate_task


@procrastinate_task(
    cron=ProcrastinateCron(expression="*/5 * * * *"),
)
def my_cron_task(timestamp: int) -> None:
    """Periodically check in with the health-cron system."""


# ---------------------------------------------------------------------------
# Integration-test tasks (same app, same decorator)
# ---------------------------------------------------------------------------


@procrastinate_task(
    cron=ProcrastinateCron(expression="*/5 * * * *"),
)
def sync_success(timestamp: int) -> None:
    """Test task: sync, succeeds."""


@procrastinate_task(
    cron=ProcrastinateCron(expression="*/5 * * * *"),
)
def sync_fail(timestamp: int) -> None:
    """Test task: sync, raises."""
    msg = "sync failure"
    raise ValueError(msg)


@procrastinate_task(
    cron=ProcrastinateCron(expression="*/5 * * * *"),
)
async def async_success(timestamp: int) -> None:
    """Test task: async, succeeds."""


@procrastinate_task(
    cron=ProcrastinateCron(expression="*/5 * * * *"),
)
async def async_fail(timestamp: int) -> None:
    """Test task: async, raises."""
    msg = "async failure"
    raise ValueError(msg)


@procrastinate_task()
def sync_traced(timestamp: int) -> None:
    """Test task: sync, opens a Sentry span in its body."""
    from whealth.auto_sentry import start_span

    with start_span(op="test.inner", name="inner-sync"):
        pass


@procrastinate_task()
async def async_traced(timestamp: int) -> None:
    """Test task: async, opens a Sentry span in its body."""
    from whealth.auto_sentry import start_span

    with start_span(op="test.inner", name="inner-async"):
        pass


@procrastinate_task()
def sync_calls_async(timestamp: int) -> None:
    """Test task: sync body hopping back to the loop via async_to_sync.

    The worst-case double hop: procrastinate ships the sync body to a
    thread (sync_to_async), and the body immediately jumps back onto the
    event loop.  The span opened inside the coroutine must still attach
    to the job's transaction.
    """
    from asgiref.sync import async_to_sync
    from whealth.auto_sentry import start_span

    async def inner() -> None:
        with start_span(op="test.inner", name="inner-sync-to-async"):
            pass

    async_to_sync(inner)()


@procrastinate_task()
async def async_calls_sync(timestamp: int) -> None:
    """Test task: async body shipping sync work to a thread.

    The reverse hop: the async body runs on the loop and pushes a sync
    function into a thread via sync_to_async.  The span opened in that
    thread must still attach to the job's transaction.
    """
    from asgiref.sync import sync_to_async
    from whealth.auto_sentry import start_span

    def inner() -> None:
        with start_span(op="test.inner", name="inner-async-to-sync"):
            pass

    await sync_to_async(inner)()


@procrastinate_task(
    cron=ProcrastinateCron(expression="*/5 * * * *"),
)
def sync_returns_awaitable(timestamp: int) -> None:
    """Test task: *sync* def that returns a coroutine object.

    Procrastinate awaits such a return value only *after* the task
    middleware has finished — the check-in lifecycle must detect this
    shape and defer the check-out until the awaitable completes.
    """
    import asyncio

    async def body() -> None:
        await asyncio.sleep(0.05)

    return body()  # type: ignore[return-value]


@procrastinate_task(
    cron=ProcrastinateCron(expression="*/5 * * * *"),
)
def sync_returns_failing_awaitable(timestamp: int) -> None:
    """Test task: sync def returning a coroutine that raises."""

    async def body() -> None:
        msg = "awaitable failure"
        raise ValueError(msg)

    return body()  # type: ignore[return-value]


_RETRY_SEEN: set[int] = set()
"""Timestamps whose first attempt already failed (see sync_retry_once)."""


@procrastinate_task(
    cron=ProcrastinateCron(expression="*/5 * * * *"),
    retry=1,
)
def sync_retry_once(timestamp: int) -> None:
    """Test task: fails on the first attempt, succeeds on the retry."""
    if timestamp not in _RETRY_SEEN:
        _RETRY_SEEN.add(timestamp)
        msg = "first attempt fails"
        raise ValueError(msg)
