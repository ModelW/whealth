"""Tests for procrastinate tasks with check-in lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import ANY, patch

import procrastinate
import pytest
from procrastinate import testing
from whealth.cron import CheckinManager, monitor_slug, reset_checkin_manager
from whealth.models import CheckIn
from whospital_apps.tasks import async_fail, async_success, sync_fail, sync_success

if TYPE_CHECKING:
    from collections.abc import Generator


pytestmark = [pytest.mark.django_db]


@pytest.fixture
def app() -> Generator[procrastinate.App, Any]:
    """Swap the real Django app's connector for an in-memory one."""
    from procrastinate.contrib.django import procrastinate_app

    in_memory = testing.InMemoryConnector()
    with procrastinate_app.current_app.replace_connector(in_memory) as app:
        yield app


@pytest.fixture(autouse=True)
def checkin_manager() -> Generator[CheckinManager, Any]:
    """Use a fresh CheckinManager for the test and restore afterward.

    Autouse so that every test's check-in events are processed and
    drained within that test — otherwise the daemon thread writes
    CheckIn rows into the database at arbitrary points during later
    tests.
    """
    cm = CheckinManager()
    cm.start()
    reset_checkin_manager(cm)
    yield cm
    cm.queue.join()
    cm.stop()
    reset_checkin_manager()


def run_worker(app_: procrastinate.App) -> None:
    """Run pending procrastinate jobs synchronously."""
    app_.run_worker(wait=False, install_signal_handlers=False, listen_notify=False)


# ---------------------------------------------------------------------------
# Sync success
# ---------------------------------------------------------------------------


def test_sync_success_job_succeeds(app: procrastinate.App) -> None:
    """A sync task reports succeeded status after execution."""
    sync_success.defer(timestamp=1)
    run_worker(app)
    assert any(j["status"] == "succeeded" for j in app.connector.jobs.values())


def test_sync_success_checkin_created(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """CheckIn is created in DB after a successful sync task."""
    sync_success.defer(timestamp=1)
    run_worker(app)
    checkin_manager.queue.join()
    checkin = CheckIn.objects.filter(cron__slug=sync_success.name).latest("start")
    assert checkin.state == CheckIn.State.FINISHED
    assert checkin.end is not None
    assert checkin.end >= checkin.start


def test_sync_success_sentry_called(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """Sentry capture_checkin is called on start and ok for a sync success."""
    with patch("whealth.cron.capture_checkin") as mock:
        sync_success.defer(timestamp=1)
        run_worker(app)
    checkin_manager.queue.join()
    slug = monitor_slug(sync_success.name)
    mock.assert_any_call(monitor_slug=slug, status="in_progress", monitor_config=ANY)
    mock.assert_any_call(
        monitor_slug=slug,
        status="ok",
        check_in_id=ANY,
        duration=ANY,
        monitor_config=ANY,
    )


# ---------------------------------------------------------------------------
# Sync failure
# ---------------------------------------------------------------------------


def test_sync_fail_job_fails(app: procrastinate.App) -> None:
    """A sync task that raises has a failed status."""
    sync_fail.defer(timestamp=1)
    run_worker(app)
    assert any(j["status"] == "failed" for j in app.connector.jobs.values())


def test_sync_fail_checkin_created(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """CheckIn is created with FAILED state after a failing sync task."""
    sync_fail.defer(timestamp=1)
    run_worker(app)
    checkin_manager.queue.join()
    checkin = CheckIn.objects.filter(cron__slug=sync_fail.name).latest("start")
    assert checkin.state == CheckIn.State.FAILED
    assert checkin.end is not None


def test_sync_fail_sentry_called_with_error(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """Sentry capture_checkin is called with error for a failing sync task."""
    with patch("whealth.cron.capture_checkin") as mock:
        sync_fail.defer(timestamp=1)
        run_worker(app)
    checkin_manager.queue.join()
    slug = monitor_slug(sync_fail.name)
    mock.assert_any_call(monitor_slug=slug, status="in_progress", monitor_config=ANY)
    mock.assert_any_call(
        monitor_slug=slug,
        status="error",
        check_in_id=ANY,
        duration=ANY,
        monitor_config=ANY,
    )


# ---------------------------------------------------------------------------
# Async success
# ---------------------------------------------------------------------------


def test_async_success_job_succeeds(app: procrastinate.App) -> None:
    """An async task reports succeeded status after execution."""
    async_success.defer(timestamp=1)
    run_worker(app)
    assert any(j["status"] == "succeeded" for j in app.connector.jobs.values())


def test_async_success_checkin_created(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """CheckIn is created in DB after a successful async task."""
    async_success.defer(timestamp=1)
    run_worker(app)
    checkin_manager.queue.join()
    checkin = CheckIn.objects.filter(cron__slug=async_success.name).latest("start")
    assert checkin.state == CheckIn.State.FINISHED


def test_async_success_sentry_called(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """Sentry capture_checkin is called on start and ok for an async success."""
    with patch("whealth.cron.capture_checkin") as mock:
        async_success.defer(timestamp=1)
        run_worker(app)
    checkin_manager.queue.join()
    slug = monitor_slug(async_success.name)
    mock.assert_any_call(monitor_slug=slug, status="in_progress", monitor_config=ANY)
    mock.assert_any_call(
        monitor_slug=slug,
        status="ok",
        check_in_id=ANY,
        duration=ANY,
        monitor_config=ANY,
    )


# ---------------------------------------------------------------------------
# Async failure
# ---------------------------------------------------------------------------


def test_async_fail_job_fails(app: procrastinate.App) -> None:
    """An async task that raises has a failed status."""
    async_fail.defer(timestamp=1)
    run_worker(app)
    assert any(j["status"] == "failed" for j in app.connector.jobs.values())


def test_async_fail_checkin_created(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """CheckIn is created with FAILED state after a failing async task."""
    async_fail.defer(timestamp=1)
    run_worker(app)
    checkin_manager.queue.join()
    checkin = CheckIn.objects.filter(cron__slug=async_fail.name).latest("start")
    assert checkin.state == CheckIn.State.FAILED


def test_async_fail_sentry_called_with_error(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """Sentry capture_checkin is called with error for a failing async task."""
    with patch("whealth.cron.capture_checkin") as mock:
        async_fail.defer(timestamp=1)
        run_worker(app)
    checkin_manager.queue.join()
    slug = monitor_slug(async_fail.name)
    mock.assert_any_call(monitor_slug=slug, status="in_progress", monitor_config=ANY)
    mock.assert_any_call(
        monitor_slug=slug,
        status="error",
        check_in_id=ANY,
        duration=ANY,
        monitor_config=ANY,
    )


# ---------------------------------------------------------------------------
# Monitor slug normalisation
# ---------------------------------------------------------------------------


def test_monitor_slug_replaces_dots() -> None:
    """Dots (invalid in Sentry monitor slugs) are replaced by dashes."""
    assert monitor_slug("myapp.tasks.my_task") == "myapp-tasks-my_task"


def test_monitor_slug_truncates_keeping_the_end() -> None:
    """Slugs longer than 50 chars keep their tail (the task name)."""
    slug = monitor_slug("a" * 60 + ".final_task")
    assert len(slug) <= 50
    assert slug.endswith("final_task")


def test_monitor_slug_valid_charset() -> None:
    """Normalised slugs only contain allowed characters."""
    import re

    slug = monitor_slug("weird!slug@with#chars once.upon.a.time")
    assert re.fullmatch(r"[a-zA-Z0-9_-]+", slug)


# ---------------------------------------------------------------------------
# Monitor config upsert
# ---------------------------------------------------------------------------


def test_checkin_sends_monitor_config(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """The Sentry check-in carries the full monitor configuration."""
    with patch("whealth.cron.capture_checkin") as mock:
        sync_success.defer(timestamp=1)
        run_worker(app)
    checkin_manager.queue.join()

    call = next(
        c for c in mock.call_args_list if c.kwargs.get("status") == "in_progress"
    )
    config = call.kwargs["monitor_config"]
    assert config["schedule"] == {"type": "crontab", "value": "*/5 * * * *"}
    assert config["timezone"] == "UTC"
    assert config["checkin_margin"] == 5
    assert config["max_runtime"] == 10
    assert config["failure_issue_threshold"] == 2
    assert config["recovery_threshold"] == 1


def test_checkout_reports_duration(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """The closing check-in reports a non-negative duration."""
    with patch("whealth.cron.capture_checkin") as mock:
        sync_success.defer(timestamp=1)
        run_worker(app)
    checkin_manager.queue.join()

    call = next(c for c in mock.call_args_list if c.kwargs.get("status") == "ok")
    assert call.kwargs["duration"] is not None
    assert call.kwargs["duration"] >= 0


def test_checkout_closes_same_checkin(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """The closing check-in references the id returned by the opening one."""
    with patch("whealth.cron.capture_checkin", return_value="sentry-id-42") as mock:
        sync_success.defer(timestamp=1)
        run_worker(app)
    checkin_manager.queue.join()

    call = next(c for c in mock.call_args_list if c.kwargs.get("status") == "ok")
    assert call.kwargs["check_in_id"] == "sentry-id-42"


# ---------------------------------------------------------------------------
# Sentry worker middleware
# ---------------------------------------------------------------------------


def run_worker_with_sentry(app_: procrastinate.App) -> None:
    """Run pending jobs with the Sentry worker middleware installed."""
    from whealth.procrastinate import sentry_worker_middleware

    app_.run_worker(
        wait=False,
        install_signal_handlers=False,
        listen_notify=False,
        worker_middleware=[sentry_worker_middleware],
    )


def test_worker_middleware_success(app: procrastinate.App) -> None:
    """Jobs succeed normally under the Sentry worker middleware."""
    sync_success.defer(timestamp=1)
    async_success.defer(timestamp=1)
    run_worker_with_sentry(app)
    statuses = [
        j["status"]
        for j in app.connector.jobs.values()
        if j["task_name"] in (sync_success.name, async_success.name)
    ]
    assert statuses
    assert all(s == "succeeded" for s in statuses)


def test_worker_middleware_captures_and_reraises(app: procrastinate.App) -> None:
    """A task exception is captured by Sentry and still fails the job."""
    with patch("whealth.procrastinate.capture_exception") as mock:
        sync_fail.defer(timestamp=1)
        run_worker_with_sentry(app)

    captured = [c.args[0] for c in mock.call_args_list]
    assert any(isinstance(e, ValueError) for e in captured)
    assert any(
        j["status"] == "failed"
        for j in app.connector.jobs.values()
        if j["task_name"] == sync_fail.name
    )


def test_worker_middleware_wraps_in_transaction(app: procrastinate.App) -> None:
    """Each job runs inside a Sentry transaction named after the task."""
    with patch("whealth.procrastinate.start_transaction") as mock:
        sync_success.defer(timestamp=1)
        run_worker_with_sentry(app)

    names = {c.kwargs["name"] for c in mock.call_args_list}
    assert sync_success.name in names
    assert all(
        c.kwargs["op"] == "queue.task.procrastinate" for c in mock.call_args_list
    )


# ---------------------------------------------------------------------------
# Worker-wide vs per-task check-in middleware (no doubling)
# ---------------------------------------------------------------------------


def run_worker_without_middleware(app_: procrastinate.App) -> None:
    """Run pending jobs with the worker-wide check-in middleware removed."""
    from procrastinate.contrib.django.db_cleanup import (
        close_db_connections,
        close_db_connections_async,
    )

    app_.run_worker(
        wait=False,
        install_signal_handlers=False,
        listen_notify=False,
        task_middleware=[close_db_connections, close_db_connections_async],
        worker_middleware=[],
    )


def _runs_of(app_: procrastinate.App, task_name: str) -> int:
    """Count executed (non-todo) jobs of a task in the in-memory connector."""
    return sum(
        1
        for j in app_.connector.jobs.values()  # type: ignore[attr-defined]
        if j["task_name"] == task_name and j["status"] != "todo"
    )


def test_checkin_not_doubled_with_worker_wide_middleware(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """With worker-wide middleware installed, one check-in per run — not two."""
    before = CheckIn.objects.filter(cron__slug=sync_success.name).count()
    sync_success.defer(timestamp=1)
    run_worker(app)
    checkin_manager.queue.join()
    after = CheckIn.objects.filter(cron__slug=sync_success.name).count()
    assert after - before == _runs_of(app, sync_success.name)


def test_fallback_checkin_without_worker_wide_middleware(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """Without worker-wide middleware, the per-task fallback checks in."""
    before = CheckIn.objects.filter(cron__slug=sync_success.name).count()
    sync_success.defer(timestamp=1)
    run_worker_without_middleware(app)
    checkin_manager.queue.join()
    after = CheckIn.objects.filter(cron__slug=sync_success.name).count()
    assert after - before == _runs_of(app, sync_success.name)


def test_fallback_checkin_async_without_worker_wide_middleware(
    app: procrastinate.App,
    checkin_manager: CheckinManager,
) -> None:
    """The async fallback also checks in when worker-wide middleware is absent."""
    before = CheckIn.objects.filter(cron__slug=async_success.name).count()
    async_success.defer(timestamp=1)
    run_worker_without_middleware(app)
    checkin_manager.queue.join()
    after = CheckIn.objects.filter(cron__slug=async_success.name).count()
    assert after - before == _runs_of(app, async_success.name)


def test_install_middleware_is_idempotent() -> None:
    """Calling install_middleware twice doesn't stack middleware."""
    from whealth.procrastinate import (
        checkin_async_middleware,
        checkin_sync_middleware,
        install_middleware,
        sentry_worker_middleware,
    )

    class FakeApp:
        worker_defaults: dict = {}  # noqa: RUF012

    fake = FakeApp()
    fake.worker_defaults = {}
    install_middleware(fake)
    install_middleware(fake)

    assert fake.worker_defaults["task_middleware"] == [
        checkin_sync_middleware,
        checkin_async_middleware,
    ]
    assert fake.worker_defaults["worker_middleware"] == [sentry_worker_middleware]


def test_middleware_auto_installed_on_django_app() -> None:
    """WhealthConfig.ready() wires the middleware into the Django app."""
    from procrastinate.contrib.django import app as django_app
    from whealth.procrastinate import (
        checkin_async_middleware,
        checkin_sync_middleware,
        sentry_worker_middleware,
    )

    task_mw = django_app.worker_defaults.get("task_middleware") or []
    worker_mw = django_app.worker_defaults.get("worker_middleware") or []
    assert checkin_sync_middleware in task_mw
    assert checkin_async_middleware in task_mw
    assert sentry_worker_middleware in worker_mw


# ---------------------------------------------------------------------------
# Transaction coverage across procrastinate's sync/async compat layer
# ---------------------------------------------------------------------------
#
# These tests use a *real* sentry_sdk client with a capturing transport and
# run tasks through the real worker. They demonstrate that the transaction
# opened by sentry_worker_middleware (on the event loop) properly covers the
# task body:
#
# - async tasks run directly on the event loop;
# - sync tasks are shipped to a thread by procrastinate via asgiref's
#   sync_to_async — contextvars (and therefore Sentry's current scope/span)
#   must propagate through that hop.
#
# In both cases, a span opened *inside the task body* must be recorded as a
# child of the middleware's transaction.


@pytest.fixture
def sentry_events() -> Generator[list[dict[str, Any]], Any]:
    """Initialise a real Sentry client capturing envelopes in-memory."""
    import sentry_sdk
    from sentry_sdk.transport import Transport

    events: list[dict[str, Any]] = []

    class CapturingTransport(Transport):
        def capture_envelope(self, envelope: Any) -> None:
            event = envelope.get_transaction_event() or envelope.get_event()
            if event is not None:
                events.append(event)

    sentry_sdk.init(
        dsn="http://key@localhost/1",
        traces_sample_rate=1.0,
        transport=CapturingTransport(),
    )
    yield events
    sentry_sdk.get_global_scope().set_client(None)


def _transaction_named(events: list[dict[str, Any]], name: str) -> dict[str, Any]:
    """Return the single transaction event with the given name."""
    matches = [
        e
        for e in events
        if e.get("type") == "transaction" and e.get("transaction") == name
    ]
    assert len(matches) == 1, f"expected 1 transaction {name!r}, got {len(matches)}"
    return matches[0]


def test_transaction_covers_sync_task_body(
    app: procrastinate.App,
    sentry_events: list[dict[str, Any]],
) -> None:
    """A span opened inside a *sync* task body attaches to the transaction.

    Sync tasks cross procrastinate's sync_to_async thread hop; the span
    must still land in the middleware's transaction.
    """
    from whospital_apps.tasks import sync_traced

    sync_traced.defer(timestamp=1)
    run_worker(app)

    txn = _transaction_named(sentry_events, sync_traced.name)
    assert txn["contexts"]["trace"]["op"] == "queue.task.procrastinate"

    inner = [s for s in txn.get("spans", []) if s.get("op") == "test.inner"]
    assert len(inner) == 1
    assert inner[0]["description"] == "inner-sync"
    # The inner span is a direct child of the transaction's root span.
    assert inner[0]["parent_span_id"] == txn["contexts"]["trace"]["span_id"]
    assert inner[0]["trace_id"] == txn["contexts"]["trace"]["trace_id"]


def test_transaction_covers_async_task_body(
    app: procrastinate.App,
    sentry_events: list[dict[str, Any]],
) -> None:
    """A span opened inside an *async* task body attaches to the transaction."""
    from whospital_apps.tasks import async_traced

    async_traced.defer(timestamp=1)
    run_worker(app)

    txn = _transaction_named(sentry_events, async_traced.name)
    assert txn["contexts"]["trace"]["op"] == "queue.task.procrastinate"

    inner = [s for s in txn.get("spans", []) if s.get("op") == "test.inner"]
    assert len(inner) == 1
    assert inner[0]["description"] == "inner-async"
    assert inner[0]["parent_span_id"] == txn["contexts"]["trace"]["span_id"]
    assert inner[0]["trace_id"] == txn["contexts"]["trace"]["trace_id"]


def test_transactions_are_isolated_between_jobs(
    app: procrastinate.App,
    sentry_events: list[dict[str, Any]],
) -> None:
    """Each job gets its own transaction with a distinct trace id."""
    from whospital_apps.tasks import async_traced, sync_traced

    sync_traced.defer(timestamp=1)
    async_traced.defer(timestamp=1)
    run_worker(app)

    sync_txn = _transaction_named(sentry_events, sync_traced.name)
    async_txn = _transaction_named(sentry_events, async_traced.name)
    assert (
        sync_txn["contexts"]["trace"]["trace_id"]
        != async_txn["contexts"]["trace"]["trace_id"]
    )


def test_transaction_marked_failed_on_sync_exception(
    app: procrastinate.App,
    sentry_events: list[dict[str, Any]],
) -> None:
    """A failing sync task produces an error event tied to its transaction."""
    sync_fail.defer(timestamp=1)
    run_worker(app)

    txns = [
        e
        for e in sentry_events
        if e.get("type") == "transaction" and e.get("transaction") == sync_fail.name
    ]
    errors = [
        e
        for e in sentry_events
        if e.get("type") != "transaction"
        and e.get("exception", {}).get("values", [{}])[0].get("value") == "sync failure"
    ]
    assert txns, "transaction missing for failed sync task"
    assert errors, "error event missing for failed sync task"
    # The error is part of the same trace as the transaction.
    assert (
        errors[0]["contexts"]["trace"]["trace_id"]
        == txns[0]["contexts"]["trace"]["trace_id"]
    )
