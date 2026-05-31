"""Tests for procrastinate tasks with check-in lifecycle."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from unittest.mock import ANY, patch

import procrastinate
import pytest
from procrastinate import testing
from whealth.cron import CheckinManager, reset_checkin_manager
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


@pytest.fixture
def checkin_manager() -> Generator[CheckinManager, Any]:
    """Use a fresh CheckinManager for the test and restore afterward."""
    cm = CheckinManager()
    cm.start()
    reset_checkin_manager(cm)
    yield cm
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
    mock.assert_any_call(monitor_slug=sync_success.name, status="in_progress")
    mock.assert_any_call(monitor_slug=sync_success.name, status="ok", check_in_id=ANY)


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
    mock.assert_any_call(monitor_slug=sync_fail.name, status="in_progress")
    mock.assert_any_call(monitor_slug=sync_fail.name, status="error", check_in_id=ANY)


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
    mock.assert_any_call(monitor_slug=async_success.name, status="in_progress")
    mock.assert_any_call(monitor_slug=async_success.name, status="ok", check_in_id=ANY)


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
    mock.assert_any_call(monitor_slug=async_fail.name, status="in_progress")
    mock.assert_any_call(monitor_slug=async_fail.name, status="error", check_in_id=ANY)
