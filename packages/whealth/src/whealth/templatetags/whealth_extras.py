"""Template filters for whealth views."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django import template

if TYPE_CHECKING:
    import datetime
    from collections.abc import Iterator

    from whealth.runner import ControlRunner

register = template.Library()


@register.filter
def run_status(result: Any) -> str:
    """Return the status label for a run result value."""
    match result:
        case False:
            return "blocked"
        case []:
            return "pass"
        case _:
            return "fail"


@register.filter
def duration_to_human(duration: datetime.timedelta | None) -> str:
    """Format a timedelta for display."""
    if duration is None:
        return "\u2014"
    total_sec = int(duration.total_seconds())
    ms = duration.microseconds // 1000
    if total_sec < 1:
        return f"{ms}ms"
    if total_sec < 60:
        return f"{total_sec}s"
    return f"{total_sec // 60}m {total_sec % 60}s"


@register.filter
def results_with_controller(
    runner: ControlRunner,
) -> Iterator[dict[str, Any]]:
    """Yield result rows with controller lookups for the template."""
    for (app_label, slug), result in runner.results.items():
        if controller := runner.registry.get(app_label, slug):
            yield dict(
                app_label=app_label,
                slug=slug,
                controller=controller,
                result=result,
            )
