"""Tests for the impact_timeline template tag."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from django.template import Context, Template
from whealth.models import RunRecord

pytestmark = [pytest.mark.django_db(transaction=True, serialized_rollback=True)]


@pytest.fixture(autouse=True)
def _clear_runs() -> None:
    """Ensure a clean slate before each test (DB isolation isn't enough)."""
    RunRecord.objects.all().delete()


def _dt(s: str) -> datetime:
    """Parse ISO string and make timezone-aware (assumes UTC)."""
    dt = datetime.fromisoformat(s)
    return dt.replace(tzinfo=UTC)


def _delta(s: str) -> timedelta:
    """Parse a ``H:MM:SS[.ffffff]`` string into a timedelta."""
    hours, minutes, rest = s.split(":")
    return timedelta(hours=int(hours), minutes=int(minutes), seconds=float(rest))


def _run(**kw: object) -> RunRecord:
    date_start = kw.get("date_start", _dt("2026-06-01 22:00:00"))
    duration = _delta(str(kw.get("duration", "0:00:00.010000")))
    return RunRecord.objects.create(
        date_start=date_start,
        date_end=date_start + duration,
        hostname="carter",
        results=kw.get("results", {}),
        impact=kw.get("impact", "none"),
    )


def _render(now: datetime) -> str:
    t = Template("{% load impact_timeline %}{% impact_timeline now=now %}")
    return t.render(Context({"now": now}))


def _bucket_classes(html: str) -> list[str]:
    """Return list of CSS class attribute values from tl-cell divs."""
    classes: list[str] = []
    for part in html.split('class="tl-cell ')[1:]:
        cls = part.split('"')[0]
        classes.append(cls)
    return classes


NOW = _dt("2026-06-01 22:30:00")


def test_no_runs_all_nodata() -> None:
    """When there are no runs every bucket should be tl-nodata."""
    html = _render(NOW)
    classes = _bucket_classes(html)
    assert len(classes) == 60
    assert all(c == "tl-nodata" for c in classes)


def test_single_run_colors_one_bucket() -> None:
    """A run 30 minutes ago colours its minute bucket tl-ok."""
    _run(date_start=_dt("2026-06-01 22:00:00"), impact="none")
    html = _render(NOW)
    classes = _bucket_classes(html)
    assert classes.count("tl-ok") == 1
    assert classes.count("tl-nodata") == 59


def test_critical_run_is_tl_critical() -> None:
    """A critical run produces a tl-critical bucket."""
    _run(date_start=_dt("2026-06-01 22:00:00"), impact="critical")
    html = _render(NOW)
    classes = _bucket_classes(html)
    assert "tl-critical" in classes


def test_highest_impact_wins_overlap() -> None:
    """When runs overlap, the higher impact fills the overlapping bucket."""
    _run(date_start=_dt("2026-06-01 22:00:00"), duration="0:00:02", impact="minor")
    _run(date_start=_dt("2026-06-01 22:00:00"), duration="0:00:02", impact="critical")
    html = _render(NOW)
    classes = _bucket_classes(html)
    assert "tl-critical" in classes
    assert "tl-minor" not in classes


def test_run_outside_window_ignored() -> None:
    """A run older than 60 minutes does not appear in the timeline."""
    _run(date_start=_dt("2026-06-01 20:00:00"), impact="none")
    html = _render(NOW)
    classes = _bucket_classes(html)
    assert all(c == "tl-nodata" for c in classes)


def test_run_mid_window_multiple_minutes() -> None:
    """A run lasting several minutes fills multiple consecutive buckets."""
    _run(date_start=_dt("2026-06-01 22:00:00"), duration="0:05:00", impact="none")
    html = _render(NOW)
    classes = _bucket_classes(html)
    assert classes.count("tl-ok") == 5


def test_legend_items_present() -> None:
    """All legend labels appear."""
    html = _render(NOW)
    assert "No Data" in html
    assert "Operational" in html
    assert "Critical" in html
