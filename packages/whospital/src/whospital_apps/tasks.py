"""Procrastinate tasks for health-check crons."""

from __future__ import annotations

from procrastinate.contrib.django import app
from whealth.procrastinate import ProcrastinateCron, procrastinate_task


@procrastinate_task(
    app=app,
    cron=ProcrastinateCron(expression="*/5 * * * *"),
    queue="health",
)
def my_cron_task(timestamp: int) -> None:
    """Periodically check in with the health-cron system."""


# ---------------------------------------------------------------------------
# Integration-test tasks (same app, same decorator)
# ---------------------------------------------------------------------------


@procrastinate_task(
    app=app,
    cron=ProcrastinateCron(expression="*/5 * * * *"),
    queue="test",
)
def sync_success(timestamp: int) -> None:
    """Test task: sync, succeeds."""


@procrastinate_task(
    app=app,
    cron=ProcrastinateCron(expression="*/5 * * * *"),
    queue="test",
)
def sync_fail(timestamp: int) -> None:
    """Test task: sync, raises."""
    msg = "sync failure"
    raise ValueError(msg)


@procrastinate_task(
    app=app,
    cron=ProcrastinateCron(expression="*/5 * * * *"),
    queue="test",
)
async def async_success(timestamp: int) -> None:
    """Test task: async, succeeds."""


@procrastinate_task(
    app=app,
    cron=ProcrastinateCron(expression="*/5 * * * *"),
    queue="test",
)
async def async_fail(timestamp: int) -> None:
    """Test task: async, raises."""
    msg = "async failure"
    raise ValueError(msg)
