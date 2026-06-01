"""Tests for the recap HTML view — content consistency."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.urls import reverse
from django.utils import timezone
from whealth import BaseControl, Failure
from whealth.controls.database import Control as DatabaseControl
from whealth.models import RunRecord
from whealth.registry import ControlInfo, ControlRegistry, Manifest

if TYPE_CHECKING:
    from django.test import Client

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


@pytest.fixture(autouse=True)
def _cleanup_db() -> None:
    """Clear run records to ensure isolation."""
    RunRecord.objects.all().delete()


@pytest.fixture
def patch_registry(monkeypatch: pytest.MonkeyPatch) -> ControlRegistry:
    """Patch the global control registry with impact-annotated test controls."""
    import whealth.registry

    reg = ControlRegistry()

    reg.register(
        ControlInfo(
            app_label="whealth",
            slug="database",
            title="Database",
            module="whealth.controls.database",
            control_class=DatabaseControl,
            manifest=Manifest(depends_on=(), impact="critical"),
            readme="",
        )
    )

    for slug, impact in (
        ("crit", "critical"),
        ("major", "major"),
        ("minor", "minor"),
    ):
        reg.register(
            ControlInfo(
                app_label="test_app",
                slug=slug,
                title=f"{slug.title()} Control",
                module=f"test_app.controls.{slug}",
                control_class=FailingControl,
                manifest=Manifest(depends_on=(), impact=impact),  # type: ignore[arg-type]
                readme="",
            )
        )

    monkeypatch.setattr(whealth.registry, "_cr", reg)
    return reg


def _create_run_record(results: dict) -> RunRecord:
    return RunRecord.objects.create(
        date_start=timezone.now(),
        date_end=timezone.now(),
        hostname="carter",
        results=results,
    )


def test_recap_shows_none_when_all_pass(
    admin_client: Client, patch_registry: ControlRegistry
) -> None:
    """Recap shows Fully Operational when all controls pass."""
    _create_run_record(
        {
            "whealth.database": [],
            "test_app.crit": [],
        }
    )
    resp = admin_client.get(reverse("whealth_recap"))
    content = resp.content.decode()

    assert resp.status_code == 200
    assert "Fully Operational" in content
    assert "Code: Green" in content


def test_recap_shows_critical_when_control_fails(
    admin_client: Client, patch_registry: ControlRegistry
) -> None:
    """Recap shows Critical Failure badge when a critical control fails."""
    _create_run_record(
        {
            "whealth.database": [{"key": "conn", "outcome": "error", "context": {}}],
            "test_app.minor": [],
        }
    )
    resp = admin_client.get(reverse("whealth_recap"))
    content = resp.content.decode()

    assert "Critical Failure" in content
    assert "Code: Red" in content
    assert "fail" in content
    assert "database" in content


def test_recap_shows_major_when_major_impact(
    admin_client: Client, patch_registry: ControlRegistry
) -> None:
    """Recap shows Major Dysfunction badge when a major control fails."""
    _create_run_record(
        {
            "whealth.database": [],
            "test_app.major": [{"key": "x", "outcome": "error", "context": {}}],
        }
    )
    resp = admin_client.get(reverse("whealth_recap"))
    content = resp.content.decode()

    assert "Major Dysfunction" in content
    assert "Code: Orange" in content


def test_recap_shows_minor_when_minor_impact(
    admin_client: Client, patch_registry: ControlRegistry
) -> None:
    """Recap shows Maintenance Advised badge when a minor control fails."""
    _create_run_record(
        {
            "whealth.database": [],
            "test_app.minor": [{"key": "x", "outcome": "warning", "context": {}}],
        }
    )
    resp = admin_client.get(reverse("whealth_recap"))
    content = resp.content.decode()

    assert "Maintenance Advised" in content
    assert "Code: Yellow" in content


def test_recap_highest_impact_wins(
    admin_client: Client, patch_registry: ControlRegistry
) -> None:
    """When several controls fail, the highest impact drives the badge."""
    _create_run_record(
        {
            "whealth.database": [],
            "test_app.minor": [{"key": "x", "outcome": "error", "context": {}}],
            "test_app.crit": [{"key": "y", "outcome": "error", "context": {}}],
        }
    )
    resp = admin_client.get(reverse("whealth_recap"))
    content = resp.content.decode()

    assert "Critical Failure" in content
    assert "Code: Red" in content
