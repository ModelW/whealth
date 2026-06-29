"""Management command to print the route structure for all controls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin

from django.core.management.base import BaseCommand
from django.urls import reverse

from whealth.printing import print_json
from whealth.registry import ControlRegistry, get_control_registry

if TYPE_CHECKING:
    from collections.abc import Sequence


def build_control_routes(
    registry: ControlRegistry,
    *,
    services: Sequence[str] = (),
    base_url: str | None = None,
) -> dict[str, object]:
    """Build the route dictionary for all discovered controls.

    Parameters
    ----------
    registry:
        A ``ControlRegistry`` that has already been discovered.
    services:
        Service names to include as concrete keys under ``service_restart``.
    base_url:
        Base URL to prepend to every path. Pass ``""`` or ``None`` for
        relative URLs (no base prepended).
    """
    controls = registry.get_sorted_controls()

    def fmt(path: str) -> str:
        if not base_url:
            return path
        return urljoin(base_url, path)

    per_control: dict[str, dict[str, str]] = {}
    for ctrl in controls:
        key = f"{ctrl.app_label}.{ctrl.slug}"
        per_control[key] = {
            "self": fmt(
                reverse(
                    "whealth_control_detail",
                    kwargs={"app": ctrl.app_label, "slug": ctrl.slug},
                )
            ),
            "deep": fmt(
                reverse(
                    "whealth_control_deep",
                    kwargs={"app": ctrl.app_label, "slug": ctrl.slug},
                )
            ),
        }

    template = reverse(
        "whealth_should_restart", kwargs={"service": "SERVICE_NAME"}
    ).replace("SERVICE_NAME", "{service_name}")

    service_restart: dict[str, str] = {"": fmt(template)}
    for svc in services:
        service_restart[svc] = fmt(
            reverse("whealth_should_restart", kwargs={"service": svc})
        )

    return {
        "global": {
            "recap": fmt(reverse("whealth_recap")),
            "control": fmt(reverse("whealth_control_list")),
        },
        "per_control": per_control,
        "service_restart": service_restart,
    }


class Command(BaseCommand):
    """Print the URL structure for all discovered controls."""

    help = "Print all URLs for all health controls as JSON."

    def add_arguments(self, parser: Any) -> None:
        """Add CLI flags."""
        parser.add_argument(
            "--relative",
            action="store_true",
            default=False,
            help="Output relative URLs instead of absolute.",
        )
        parser.add_argument(
            "--service",
            action="append",
            default=[],
            dest="services",
            help="Add a key to service_restart for the given service name.",
        )

    def handle(self, *args: str, **options: str) -> None:
        """Discover controls and print the route structure."""
        registry = get_control_registry()
        if registry.discovery is None:
            msg = (
                "Control discovery has not been run yet. "
                "Make sure whealth.apps.WhealthConfig is in INSTALLED_APPS."
            )
            raise RuntimeError(msg)

        if options["relative"]:
            base_url = ""
        else:
            from django.conf import settings

            base_url = (
                getattr(settings, "WHEALTH_BASE_URL", None)
                or getattr(settings, "BASE_URL", None)
                or "http://localhost:8000"
            )

        data = build_control_routes(
            registry, services=options["services"], base_url=base_url
        )
        print_json(data)
