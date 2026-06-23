"""Views for the whealth health-checking app."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import permission_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from whealth.models import Control, RunRecord


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


def control_detail(request: HttpRequest, app: str, slug: str) -> JsonResponse:
    """Return JSON with ok status for a single control from the last run."""
    latest = RunRecord.objects.order_by("-date_start").first()
    if latest is None:
        return JsonResponse({"ok": False}, status=418)

    label = f"{app}.{slug}"
    result = latest.results.get(label)
    if result is False:
        return JsonResponse({"ok": True}, status=200)

    ok = _is_ok(result)
    return JsonResponse({"ok": ok}, status=200 if ok else 418)


def control_list(request: HttpRequest) -> JsonResponse:
    """Return JSON with ok status for all controls from the last run."""
    latest = RunRecord.objects.order_by("-date_start").first()
    if latest is None:
        return JsonResponse({"ok": False}, status=418)

    all_ok = all(_is_ok(result) for result in latest.results.values())
    return JsonResponse({"ok": all_ok}, status=200 if all_ok else 418)
