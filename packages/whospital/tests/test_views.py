"""Tests for whealth health-checking views."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.urls import reverse
from django.utils import timezone
from whealth import BaseControl, Failure, RestartRemediation
from whealth.models import RunRecord
from whealth.registry import ControlInfo, ControlRegistry, Manifest

if TYPE_CHECKING:
    from django.test import Client
    from whealth.base import Remediation

pytestmark = [pytest.mark.django_db]


class PassingControl(BaseControl):
    """Control that always passes."""

    def get_failures(self) -> list[Failure]:
        """Return no failures."""
        return []


class FailingControl(BaseControl):
    """Control that always fails."""

    def get_failures(self) -> list[Failure]:
        """Return a simple failure."""
        return [Failure(key="fail", outcome="error")]


class RestartRequiredControl(BaseControl):
    """Control that returns a failure with restart remediation."""

    def get_failures(self) -> list[Failure]:
        """Return failure requiring postgresql restart."""
        return [Failure(key="db_fail", outcome="error")]

    def get_remediation(self, failure: Failure) -> Remediation | None:
        """Recommend restarting postgresql to resolve the failure."""
        return RestartRemediation(components=["postgresql"])


class BlockedControl(BaseControl):
    """Control that depends on FailingControl and is therefore blocked."""

    def get_failures(self) -> list[Failure]:
        """Return no failures of its own; it never actually runs."""
        return []


@pytest.fixture(autouse=True)
def _cleanup_db() -> None:
    """Clear run records to ensure isolation."""
    RunRecord.objects.all().delete()


@pytest.fixture
def patch_registry(monkeypatch: pytest.MonkeyPatch) -> ControlRegistry:
    """Patch the global control registry with test controls."""
    import whealth.registry

    reg = ControlRegistry()

    # Register PassingControl
    reg.register(
        ControlInfo(
            app_label="test_app",
            slug="passing",
            title="Passing Control",
            module="test_app.controls.passing",
            control_class=PassingControl,
            manifest=Manifest(depends_on=()),
            readme="",
        )
    )

    # Register FailingControl
    reg.register(
        ControlInfo(
            app_label="test_app",
            slug="failing",
            title="Failing Control",
            module="test_app.controls.failing",
            control_class=FailingControl,
            manifest=Manifest(depends_on=()),
            readme="",
        )
    )

    # Register RestartRequiredControl
    reg.register(
        ControlInfo(
            app_label="test_app",
            slug="restart",
            title="Restart Control",
            module="test_app.controls.restart",
            control_class=RestartRequiredControl,
            manifest=Manifest(depends_on=()),
            readme="",
        )
    )

    # Register BlockedControl, which depends on the failing control.
    reg.register(
        ControlInfo(
            app_label="test_app",
            slug="blocked",
            title="Blocked Control",
            module="test_app.controls.blocked",
            control_class=BlockedControl,
            manifest=Manifest(depends_on=("test_app.failing",)),
            readme="",
        )
    )

    monkeypatch.setattr(whealth.registry, "_cr", reg)
    return reg


def test_control_detail_view(client: Client, patch_registry: ControlRegistry) -> None:
    """Test the control_detail view under different conditions."""
    # 1. No RunRecord exists
    url = reverse(
        "whealth_control_detail", kwargs={"app": "test_app", "slug": "passing"}
    )
    res = client.get(url)
    assert res.status_code == 404

    # Create a RunRecord with passing, failing, and skipped controls
    results = {
        "test_app.passing": [],
        "test_app.failing": [{"key": "fail", "outcome": "error"}],
        "test_app.skipped": False,
    }
    RunRecord.objects.create(
        date_start=timezone.now(),
        date_end=timezone.now(),
        hostname="localhost",
        results=results,
    )

    # Passing control -> 200 OK
    url = reverse(
        "whealth_control_detail", kwargs={"app": "test_app", "slug": "passing"}
    )
    res = client.get(url)
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    # Failing control -> 418
    url = reverse(
        "whealth_control_detail", kwargs={"app": "test_app", "slug": "failing"}
    )
    res = client.get(url)
    assert res.status_code == 418
    assert res.json() == {"ok": False}

    # Skipped control -> 200 OK
    url = reverse(
        "whealth_control_detail", kwargs={"app": "test_app", "slug": "skipped"}
    )
    res = client.get(url)
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    # Non-existent control -> 404
    url = reverse(
        "whealth_control_detail", kwargs={"app": "test_app", "slug": "nonexistent"}
    )
    res = client.get(url)
    assert res.status_code == 404


def test_control_deep_view(client: Client, patch_registry: ControlRegistry) -> None:
    """Test the control_deep view under different conditions."""
    # 1. No RunRecord exists -> 404
    url = reverse("whealth_control_deep", kwargs={"app": "test_app", "slug": "passing"})
    res = client.get(url)
    assert res.status_code == 404

    # Create a RunRecord
    results = {
        "test_app.passing": [],
        "test_app.failing": [{"key": "fail", "outcome": "error"}],
        "test_app.blocked": False,
    }
    RunRecord.objects.create(
        date_start=timezone.now(),
        date_end=timezone.now(),
        hostname="localhost",
        results=results,
    )

    # 2. Passing control -> 200 OK
    url = reverse("whealth_control_deep", kwargs={"app": "test_app", "slug": "passing"})
    res = client.get(url)
    assert res.status_code == 200
    assert res.json() == {"ok": True}

    # 3. Failing control -> 418
    url = reverse("whealth_control_deep", kwargs={"app": "test_app", "slug": "failing"})
    res = client.get(url)
    assert res.status_code == 418
    assert res.json() == {"ok": False}

    # 4. Blocked control -> 418 because a failing ancestor makes it untrustworthy
    #    (Unlike control_detail, which returns 200 for the blocked control itself.)
    url = reverse("whealth_control_deep", kwargs={"app": "test_app", "slug": "blocked"})
    res = client.get(url)
    assert res.status_code == 418
    assert res.json() == {"ok": False}

    # 5. Non-existent control -> 404
    url = reverse(
        "whealth_control_deep", kwargs={"app": "test_app", "slug": "nonexistent"}
    )
    res = client.get(url)
    assert res.status_code == 404


def test_should_restart_view(client: Client, patch_registry: ControlRegistry) -> None:
    """Test the should_restart view under different conditions."""
    # 1. No RunRecord exists
    url = reverse("whealth_should_restart", kwargs={"service": "postgresql"})
    res = client.get(url)
    assert res.status_code == 404

    # Create a RunRecord where only the passing control ran
    RunRecord.objects.create(
        date_start=timezone.now(),
        date_end=timezone.now(),
        hostname="localhost",
        results={"test_app.passing": []},
    )

    # 2. No failures, so no restart is needed
    url = reverse("whealth_should_restart", kwargs={"service": "postgresql"})
    res = client.get(url)
    assert res.status_code == 200
    assert res.json() == {"should_restart": False}

    # Update RunRecord to include the failed control requiring restart
    RunRecord.objects.all().delete()
    RunRecord.objects.create(
        date_start=timezone.now(),
        date_end=timezone.now(),
        hostname="localhost",
        results={
            "test_app.passing": [],
            "test_app.restart": [{"key": "db_fail", "outcome": "error"}],
        },
    )

    # 3. Querying the correct service -> should_restart is True
    url = reverse("whealth_should_restart", kwargs={"service": "postgresql"})
    res = client.get(url)
    assert res.status_code == 418
    assert res.json() == {"should_restart": True}

    # 4. Querying a different service -> should_restart is False
    url = reverse("whealth_should_restart", kwargs={"service": "redis"})
    res = client.get(url)
    assert res.status_code == 200
    assert res.json() == {"should_restart": False}
