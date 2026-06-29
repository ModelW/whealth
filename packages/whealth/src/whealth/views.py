"""Views for the whealth health-checking app."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from django.contrib.auth.decorators import permission_required
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from whealth.models import Control, RunRecord

if TYPE_CHECKING:
    from whealth.runner import ControlRunner

logger = logging.getLogger("whealth.views")


def _human_duration(duration: Any) -> str:
    """Format a duration for display."""
    if duration is None:
        return "\u2014"
    total_sec = int(duration.total_seconds())
    ms = duration.microseconds // 1000
    if total_sec < 1:
        return f"{ms}ms"
    if total_sec < 60:
        return f"{total_sec}s"
    return f"{total_sec // 60}m {total_sec % 60}s"


def _is_ok(result: Any) -> bool:
    """Return True if the control result is passing.

    ``result is False`` means the control was blocked by a dependency —
    its own check never ran, so it is considered ok.
    """
    if result is False:
        return True
    if not result:
        return True
    return not any(f.get("outcome") in ("error", "internal_error") for f in result)


@permission_required(
    ["whealth.view_control", "whealth.view_incident", "whealth.view_cron"],
    raise_exception=True,
)
def recap(request: HttpRequest) -> HttpResponse:
    """Display a table with the recap of the most recent run."""
    latest = RunRecord.objects.order_by("-date_start").first()
    rows: list[dict[str, Any]] = []

    if latest is not None:
        for label, result in latest.results.items():
            app_label, slug = label.split(".", 1)
            try:
                control = Control.objects.get(app_label=app_label, slug=slug)
            except Control.DoesNotExist:
                control = None

            if result is False:
                status = "blocked"
            elif not result:
                status = "pass"
            else:
                status = "fail"

            rows.append(
                {
                    "slug": slug,
                    "title": control.title if control else slug,
                    "app_label": app_label,
                    "status": status,
                    "failures": result if isinstance(result, list) else [],
                }
            )

    return render(
        request,
        "whealth/recap.html",
        {
            "run": latest,
            "duration_display": _human_duration(latest.duration if latest else None),
            "rows": rows,
        },
    )


def _get_runner_for(key: tuple[str, str] | None = None) -> ControlRunner:
    """Return the runner for a control."""
    latest = RunRecord.objects.order_by("-date_start").first()

    if latest is None:
        msg = "No run record found"
        raise Http404(msg)

    if key and f"{key[0]}.{key[1]}" not in latest.results:
        msg = "Control not found"
        raise Http404(msg)

    return latest.get_runner()


def control_detail(request: HttpRequest, app: str, slug: str) -> JsonResponse:
    """Return JSON with ok status for a single control from the last run."""
    runner = _get_runner_for((app, slug))
    ok = runner.is_control_ok(app, slug)
    return JsonResponse({"ok": ok}, status=200 if ok else 418)


def control_list(request: HttpRequest) -> JsonResponse:
    """Return JSON with ok status for all controls from the last run."""
    runner = _get_runner_for()
    all_ok = runner.is_ok()
    return JsonResponse({"ok": all_ok}, status=200 if all_ok else 418)


def control_deep(request: HttpRequest, app: str, slug: str) -> JsonResponse:
    """Return JSON with ok status for a single control, only if it is OK.

    Returns 418 if the control was skipped.
    """
    runner = _get_runner_for((app, slug))
    ok = runner.is_control_deep_ok(app, slug)
    return JsonResponse({"ok": ok}, status=200 if ok else 418)


def should_restart(request: HttpRequest, service: str) -> JsonResponse:
    """Return whether restarting a specific service will resolve active issues."""
    runner = _get_runner_for()
    should = runner.should_restart_service(service)
    return JsonResponse({"should_restart": should}, status=418 if should else 200)
