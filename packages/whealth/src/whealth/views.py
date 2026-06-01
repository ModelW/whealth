"""Views for the whealth health-checking app."""

from __future__ import annotations

from typing import Any

from django.contrib.auth.decorators import permission_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from whealth.models import Control, Incident, RunRecord


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


def _latest_run_with_ignored() -> tuple[RunRecord | None, set[str]]:
    """Return the most recent run and the set of ignored control keys."""
    run = RunRecord.objects.order_by("-date_start").first()
    ignored = set(
        Incident.objects.filter(
            date_end__isnull=True, date_ignored__isnull=False
        ).values_list("control__app_label", "control__slug")
    )
    return run, {f"{app}.{slug}" for app, slug in ignored}


def _is_ok(label: str, result: Any, ignored: set[str]) -> bool:
    """Return True if the control result is passing or its failures are ignored."""
    if result is None:
        return False
    if not result:
        return True
    if label in ignored:
        return True
    return not any(f.get("outcome") in ("error", "internal_error") for f in result)


def _filter_ignored(label: str, result: Any, ignored: set[str]) -> list[dict[str, Any]]:
    """Return failures with ignored incidents removed. Returns empty list for pass."""
    if not isinstance(result, list):
        return []
    if label not in ignored:
        return result
    return []


@permission_required(
    ["whealth.view_control", "whealth.view_incident", "whealth.view_cron"],
    raise_exception=True,
)
def recap(request: HttpRequest) -> HttpResponse:
    """Display a table with the recap of the most recent run."""
    latest, ignored = _latest_run_with_ignored()
    rows: list[dict[str, Any]] = []

    if latest is not None:
        for label, result in latest.results.items():
            app_label, slug = label.split(".", 1)
            try:
                control = Control.objects.get(app_label=app_label, slug=slug)
            except Control.DoesNotExist:
                control = None

            failures = _filter_ignored(label, result, ignored)

            if result is None:
                status = "blocked"
            elif not failures:
                status = "pass"
            else:
                status = "fail"

            rows.append(
                {
                    "slug": slug,
                    "title": control.title if control else slug,
                    "app_label": app_label,
                    "status": status,
                    "failures": failures,
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
    latest, ignored = _latest_run_with_ignored()
    if latest is None:
        return JsonResponse({"ok": False}, status=418)

    label = f"{app}.{slug}"
    result = latest.results.get(label)
    if result is None:
        return JsonResponse({"ok": False}, status=404)

    ok = _is_ok(label, result, ignored)
    return JsonResponse({"ok": ok}, status=200 if ok else 418)


def control_list(request: HttpRequest) -> JsonResponse:
    """Return JSON with ok status for all controls from the last run."""
    latest, ignored = _latest_run_with_ignored()
    if latest is None:
        return JsonResponse({"ok": False}, status=418)

    all_ok = all(
        _is_ok(label, result, ignored) for label, result in latest.results.items()
    )
    return JsonResponse({"ok": all_ok}, status=200 if all_ok else 418)
