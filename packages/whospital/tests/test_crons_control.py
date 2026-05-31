"""Tests for the Cron Schedule health control (crons control)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from croniter import croniter  # type: ignore[import-untyped]
from django.utils.timezone import now as django_now
from freezegun import freeze_time
from whealth.controls.crons import _evaluate_cron
from whealth.models import CheckIn, Cron

pytestmark = [pytest.mark.django_db]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def cron() -> Cron:
    """Create a ``*/5 * * * *`` cron with default threshold = 2, margin = 2 min."""
    return Cron.objects.create(
        slug="test-cron",
        schedule_type=Cron.ScheduleType.CRONTAB,
        schedule="*/5 * * * *",
        timezone="UTC",
        checkin_margin=timedelta(minutes=2),
        max_runtime=timedelta(minutes=1),
        failure_issue_threshold=2,
        recovery_threshold=1,
    )


@pytest.fixture
def slots(cron: Cron) -> list[datetime]:
    """Return the last 20 scheduled crontab times before *now*.

    Uses ``django_now()`` which is frozen when ``freeze_time`` is active.
    """
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    return [it.get_prev(datetime) for _ in range(20)]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_no_checkins_ever(cron: Cron) -> None:
    """No CheckIn rows at all → should fail."""
    failure = _evaluate_cron(cron)
    assert failure is not None
    assert failure.key == "test-cron"
    assert failure.outcome == "error"


@freeze_time("2026-06-01 12:00:00")
def test_single_hit_no_misses(cron: Cron) -> None:
    """One successful check-in on the most recent slot → healthy."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    slot = it.get_prev(datetime)
    CheckIn.objects.create(
        cron=cron, start=slot, state=CheckIn.State.FINISHED, end=slot
    )
    assert _evaluate_cron(cron) is None


@freeze_time("2026-06-01 12:00:00")
def test_two_consecutive_hits(cron: Cron) -> None:
    """Two successful check-ins → healthy."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    for _ in range(2):
        s = it.get_prev(datetime)
        CheckIn.objects.create(cron=cron, start=s, state=CheckIn.State.FINISHED, end=s)
    assert _evaluate_cron(cron) is None


@freeze_time("2026-06-01 12:00:00")
def test_one_miss_below_threshold(cron: Cron) -> None:
    """One missed slot but threshold is 2 → healthy."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    it.get_prev(datetime)  # most recent — miss
    slot = it.get_prev(datetime)  # second most recent — hit
    CheckIn.objects.create(
        cron=cron, start=slot, state=CheckIn.State.FINISHED, end=slot
    )
    assert _evaluate_cron(cron) is None


@freeze_time("2026-06-01 12:00:00")
def test_two_consecutive_misses_breaches_threshold(cron: Cron) -> None:
    """Two consecutive missed slots → failure."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    it.get_prev(datetime)  # miss
    it.get_prev(datetime)  # miss
    slot = it.get_prev(datetime)  # hit
    CheckIn.objects.create(
        cron=cron, start=slot, state=CheckIn.State.FINISHED, end=slot
    )
    failure = _evaluate_cron(cron)
    assert failure is not None


@freeze_time("2026-06-01 12:00:00")
def test_recovery_after_misses(cron: Cron) -> None:
    """Two misses recovered by a hit → healthy."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    # Most recent slot — hit (success)
    slot = it.get_prev(datetime)
    CheckIn.objects.create(
        cron=cron, start=slot, state=CheckIn.State.FINISHED, end=slot
    )
    it.get_prev(datetime)  # miss
    it.get_prev(datetime)  # miss
    # hit further back resets older misses, but we only care about recent ones
    s = it.get_prev(datetime)
    CheckIn.objects.create(cron=cron, start=s, state=CheckIn.State.FINISHED, end=s)
    assert _evaluate_cron(cron) is None


def test_three_consecutive_misses_with_threshold_two(cron: Cron) -> None:
    """Three misses → failure."""
    failure = _evaluate_cron(cron)
    assert failure is not None


def test_failed_checkin_counts_as_miss(cron: Cron) -> None:
    """A FAILED check-in counts as a miss."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    it.get_prev(datetime)  # miss
    s = it.get_prev(datetime)  # started but failed
    CheckIn.objects.create(cron=cron, start=s, state=CheckIn.State.FAILED, end=s)
    # Most recent slot is a miss, and the one behind it is failed → 2 misses → fail
    failure = _evaluate_cron(cron)
    assert failure is not None


@freeze_time("2026-06-01 12:00:00")
def test_checkin_within_margin_still_counts(cron: Cron) -> None:
    """Check-in that arrives *early* (within margin before the slot) hits."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    slot = it.get_prev(datetime)
    early = slot - timedelta(minutes=8)
    cron.checkin_margin = timedelta(minutes=10)
    cron.save()
    CheckIn.objects.create(
        cron=cron, start=early, state=CheckIn.State.FINISHED, end=early
    )
    assert _evaluate_cron(cron) is None


@freeze_time("2026-06-01 12:00:00")
def test_checkin_just_past_margin_counts_as_miss(cron: Cron) -> None:
    """Check-in past margin → miss, but recent slot has a hit, so healthy."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    # Hit at the most recent slot
    latest_slot = it.get_prev(datetime)
    CheckIn.objects.create(
        cron=cron, start=latest_slot, state=CheckIn.State.FINISHED, end=latest_slot
    )
    # Check-in 3 min after *this* slot — too late to cover it, but that's fine
    slot = it.get_prev(datetime)
    late = slot + timedelta(minutes=3)
    CheckIn.objects.create(
        cron=cron, start=late, state=CheckIn.State.FINISHED, end=late
    )
    assert _evaluate_cron(cron) is None


@freeze_time("2026-06-01 12:00:00")
def test_checkin_past_runtime_counts_as_miss(cron: Cron) -> None:
    """Check-in past runtime → miss, but recent slot has a hit, so healthy."""
    it = croniter(cron.schedule, django_now(), ret_type=datetime)
    # Hit at the most recent slot
    latest_slot = it.get_prev(datetime)
    CheckIn.objects.create(
        cron=cron, start=latest_slot, state=CheckIn.State.FINISHED, end=latest_slot
    )
    slot = it.get_prev(datetime)
    late = slot + timedelta(minutes=5)
    CheckIn.objects.create(
        cron=cron, start=late, state=CheckIn.State.FINISHED, end=late
    )
    assert _evaluate_cron(cron) is None
