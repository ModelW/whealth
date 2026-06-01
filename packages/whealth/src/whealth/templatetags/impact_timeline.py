"""Template tag rendering a 1-hour impact timeline for the recap page."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django import template
from django.utils.safestring import mark_safe
from django.utils.timezone import now as django_now

from whealth.models import RunRecord

register = template.Library()

_WINDOW_MINUTES = 60


@register.simple_tag
def impact_timeline(now: Any = None) -> str:
    """Render a 1-hour horizontal timeline as an HTML string.

    Each cell represents one minute.  Colour reflects the impact of
    whichever run was active at that minute (most recent run wins on
    overlap).

    Pass *now* explicitly to freeze time for tests.
    """
    if now is None:
        now = django_now()
    window_start = now - timedelta(minutes=_WINDOW_MINUTES)

    buckets: list[str | None] = [None] * _WINDOW_MINUTES

    runs = list(
        RunRecord.objects.filter(date_start__gte=window_start)
        .order_by("-date_start")
        .values("date_start", "duration", "impact")
    )

    for run in runs:
        start = run["date_start"]
        end = start + (run["duration"] or timedelta(minutes=1))

        start_idx = _idx(window_start, start)
        end_idx = _idx(window_start, end)

        if end_idx == start_idx:
            end_idx = start_idx + 1
        for idx in range(start_idx, min(_WINDOW_MINUTES, end_idx)):
            if idx < 0:
                continue
            if buckets[idx] is None or _rank(run["impact"]) > _rank(buckets[idx]):
                buckets[idx] = run["impact"]

    return _render(buckets)


def _idx(window_start: Any, ts: Any) -> int:
    return int((ts - window_start).total_seconds() // 60)


def _rank(impact: str | None) -> int:
    if impact is None:
        return -1
    return {"none": 0, "minor": 1, "major": 2, "critical": 3}.get(impact, 0)


_CLASSES: dict[str | None, str] = {
    None: "tl-cell tl-nodata",
    "none": "tl-cell tl-ok",
    "minor": "tl-cell tl-minor",
    "major": "tl-cell tl-major",
    "critical": "tl-cell tl-critical",
}

_LABELS: dict[str | None, str] = {
    None: "No Data",
    "none": "Operational",
    "minor": "Minor",
    "major": "Major",
    "critical": "Critical",
}


def _render(buckets: list[str | None]) -> str:
    parts: list[str] = [
        '<div class="tl-grid">',
    ]

    for _, impact in enumerate(buckets):
        cls = _CLASSES.get(impact, "tl-cell tl-nodata")
        label = _LABELS.get(impact, "No Data")
        parts.append(f'<div class="{cls}" title="{label}"></div>')

    parts.append("</div>")

    legend = '<div class="tl-legend">'
    for _, cls, label in [
        (None, "tl-nodata", "No Data"),
        ("none", "tl-ok", "Operational"),
        ("minor", "tl-minor", "Minor"),
        ("major", "tl-major", "Major"),
        ("critical", "tl-critical", "Critical"),
    ]:
        legend += f'<span class="tl-dot {cls}"></span>{label}'
    legend += "</div>"

    return mark_safe("".join(parts) + legend)  # noqa: S308 — all values are hardcoded constants
