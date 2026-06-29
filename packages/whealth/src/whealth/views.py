"""Views for the whealth health-checking app."""

from __future__ import annotations

from django.contrib.auth.decorators import permission_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from whealth.registry import get_control_registry


@permission_required(
    ["whealth.view_control", "whealth.view_incident", "whealth.view_cron"],
    raise_exception=True,
)
def recap(request: HttpRequest) -> HttpResponse:
    """Display a table with the recap of the most recent run."""
    return render(
        request,
        "whealth/recap.html",
        {"runner": get_control_registry().get_recent_run()},
    )


def control_detail(request: HttpRequest, app: str, slug: str) -> JsonResponse:
    """Return JSON with ok status for a single control from the last run."""
    runner = get_control_registry().get_recent_run((app, slug))
    ok = runner.is_control_ok(app, slug)
    return JsonResponse({"ok": ok}, status=200 if ok else 418)


def control_list(request: HttpRequest) -> JsonResponse:
    """Return JSON with ok status for all controls from the last run."""
    runner = get_control_registry().get_recent_run()
    all_ok = runner.is_ok()
    return JsonResponse({"ok": all_ok}, status=200 if all_ok else 418)


def control_deep(request: HttpRequest, app: str, slug: str) -> JsonResponse:
    """Return JSON with ok status for a single control, only if it is OK.

    Returns 418 if the control was skipped.
    """
    runner = get_control_registry().get_recent_run((app, slug))
    ok = runner.is_control_deep_ok(app, slug)
    return JsonResponse({"ok": ok}, status=200 if ok else 418)


def should_restart(request: HttpRequest, service: str) -> JsonResponse:
    """Return whether restarting a specific service will resolve active issues."""
    runner = get_control_registry().get_recent_run()
    should = runner.should_restart_service(service)
    return JsonResponse({"should_restart": should}, status=418 if should else 200)
