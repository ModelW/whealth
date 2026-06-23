"""Tests for the control runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from whealth.registry import ControlInfo, ControlRegistry, Manifest

if TYPE_CHECKING:
    from whealth.runner import ControlRunner

pytestmark = [pytest.mark.django_db]

# ---------------------------------------------------------------------------
# Control metadata needed to build a non-discovery registry
# ---------------------------------------------------------------------------

_CONTROLS: dict[str, dict[str, object]] = {
    "alpha": {
        "module": "whospital_apps.controls.alpha",
        "deps": (),
        "title": None,
    },
    "beta": {
        "module": "whospital_apps.controls.beta",
        "deps": ("alpha",),
        "title": None,
    },
    "gamma": {
        "module": "whospital_apps.controls.gamma",
        "deps": ("beta",),
        "title": None,
    },
    "delta": {
        "module": "whospital_apps.controls.delta",
        "deps": ("alpha",),
        "title": None,
    },
    "epsilon": {
        "module": "whospital_apps.controls.epsilon",
        "deps": ("delta", "beta"),
        "title": None,
    },
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _cleanup_db() -> None:
    """Clear all database models before each test to ensure absolute isolation."""
    from whealth.models import CheckIn, Cron, Incident, RunRecord
    from whospital_apps.models import KeyValue

    Incident.objects.all().delete()
    RunRecord.objects.all().delete()
    CheckIn.objects.all().delete()
    Cron.objects.all().delete()
    KeyValue.objects.all().delete()


@pytest.fixture
def registry() -> ControlRegistry:
    """Return a fresh registry with all sample controls registered."""
    reg = ControlRegistry()
    for slug, meta in _CONTROLS.items():
        mod = __import__(meta["module"], fromlist=["Control"])
        app_label = meta["module"].split(".")[0]
        manifest = Manifest(depends_on=meta["deps"], title=meta["title"])
        info = ControlInfo(
            app_label=app_label,
            slug=slug,
            title=meta["title"],
            module=meta["module"],
            control_class=mod.Control,
            manifest=manifest,
            readme=f"# {slug}\n",
        )
        reg.register(info)
    return reg


@pytest.fixture
def db_registry(registry: ControlRegistry) -> ControlRegistry:
    """Return a registry synced to the database."""
    registry.sync_to_db()
    return registry


@pytest.fixture
def runner(registry: ControlRegistry) -> ControlRunner:
    """Return a runner for the given registry (not yet run)."""
    return registry.get_runner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _kv(key: str, value: str) -> None:
    """Create or update a KeyValue entry."""
    from whospital_apps.models import KeyValue

    KeyValue.objects.update_or_create(key=key, defaults={"value": value})


# ---------------------------------------------------------------------------
# Basic: all pass
# ---------------------------------------------------------------------------


def test_all_pass(runner: ControlRunner) -> None:
    """All controls pass when no KeyValue entries are set."""
    runner._run()

    for slug in ("alpha", "beta", "gamma", "delta", "epsilon"):
        result = runner.results[("whospital_apps", slug)]
        assert result == []


def test_warning_does_not_block(runner: ControlRunner) -> None:
    """A warning on alpha still allows dependents to run."""
    _kv("alpha", "warning")
    runner._run()

    result_alpha = runner.results[("whospital_apps", "alpha")]
    assert isinstance(result_alpha, list)
    assert len(result_alpha) == 1
    assert result_alpha[0].outcome == "warning"

    for slug in ("beta", "gamma", "delta", "epsilon"):
        result = runner.results[("whospital_apps", slug)]
        assert isinstance(result, list)


def test_dependent_retains_its_own_failures(runner: ControlRunner) -> None:
    """A dependent control correctly retains its own failures when it runs."""
    _kv("alpha", "warning")
    _kv("beta", "error")
    runner._run()

    result_alpha = runner.results[("whospital_apps", "alpha")]
    assert isinstance(result_alpha, list)
    assert len(result_alpha) == 1
    assert result_alpha[0].outcome == "warning"

    result_beta = runner.results[("whospital_apps", "beta")]
    assert isinstance(result_beta, list)
    assert len(result_beta) == 1
    assert result_beta[0].outcome == "error"


def test_alpha_error_blocks_dependents(runner: ControlRunner) -> None:
    """An error on alpha blocks dependents."""
    _kv("alpha", "error")
    runner._run()

    result_alpha = runner.results[("whospital_apps", "alpha")]
    assert isinstance(result_alpha, list)
    assert len(result_alpha) == 1
    assert result_alpha[0].outcome == "error"

    for slug in ("beta", "gamma", "delta", "epsilon"):
        assert runner.results[("whospital_apps", slug)] is False


def test_exception_in_control_produces_internal_error(
    runner: ControlRunner,
) -> None:
    """An exception raised by a control is caught and recorded."""
    _kv("alpha", "value_that_makes_utils_raise")
    runner._run()

    result = runner.results[("whospital_apps", "alpha")]
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0].outcome == "internal_error"
    assert "exception" in result[0].context


def test_topological_order(runner: ControlRunner) -> None:
    """Controls are run in dependency order (parents before children)."""
    runner._run()
    keys = list(runner.results.keys())

    alpha_idx = keys.index(("whospital_apps", "alpha"))
    beta_idx = keys.index(("whospital_apps", "beta"))
    gamma_idx = keys.index(("whospital_apps", "gamma"))
    delta_idx = keys.index(("whospital_apps", "delta"))
    epsilon_idx = keys.index(("whospital_apps", "epsilon"))

    assert alpha_idx < beta_idx
    assert alpha_idx < delta_idx
    assert beta_idx < gamma_idx
    assert beta_idx < epsilon_idx
    assert delta_idx < epsilon_idx


# ---------------------------------------------------------------------------
# Incident sync
# ---------------------------------------------------------------------------


def test_no_failures_creates_no_incidents(
    db_registry: ControlRegistry,
) -> None:
    """Passing controls produce no incidents."""
    from whealth.models import Incident

    runner = db_registry.get_runner()
    runner.results[("whealth", "database")] = []
    runner.run_and_sync()

    assert Incident.objects.count() == 0


def test_error_failure_creates_incident(db_registry: ControlRegistry) -> None:
    """An error on alpha creates an open incident."""
    from whealth.models import Incident

    _kv("alpha", "error")
    runner = db_registry.get_runner()
    runner.results[("whealth", "database")] = []
    runner.run_and_sync()

    incidents = Incident.objects.filter(control__slug="alpha")
    assert incidents.count() == 1
    inc = incidents.get()
    assert inc.key == "alpha"
    assert inc.date_end is None


def test_resolved_failure_closes_incident(db_registry: ControlRegistry) -> None:
    """A previously failing control that passes closes the incident."""
    from whealth.models import Incident

    _kv("alpha", "error")
    runner = db_registry.get_runner()
    runner.results[("whealth", "database")] = []
    runner.run_and_sync()
    assert (
        Incident.objects.filter(control__slug="alpha", date_end__isnull=True).count()
        == 1
    )

    # Now fix it
    from whospital_apps.models import KeyValue

    KeyValue.objects.filter(key="alpha").delete()

    runner.run_and_sync()
    inc = Incident.objects.get(control__slug="alpha")
    assert inc.date_end is not None


def test_closing_incident_does_not_affect_previously_closed_incidents(
    db_registry: ControlRegistry,
) -> None:
    """Closing an incident shouldn't touch already closed historical ones."""
    from whealth.models import Incident
    from whospital_apps.models import KeyValue

    # 1. Trigger first failure on alpha
    _kv("alpha", "error")
    runner1 = db_registry.get_runner()
    runner1.results[("whealth", "database")] = []
    runner1.run_and_sync()

    # Verify first incident is open
    inc1 = Incident.objects.get(control__slug="alpha")
    assert inc1.date_end is None

    # 2. Resolve the failure
    KeyValue.objects.filter(key="alpha").delete()
    runner1.run_and_sync()

    # Verify first incident is closed
    inc1.refresh_from_db()
    first_date_end = inc1.date_end
    assert first_date_end is not None

    # 3. Trigger second failure on alpha (same key)
    _kv("alpha", "error")
    runner2 = db_registry.get_runner()
    runner2.results[("whealth", "database")] = []
    runner2.run_and_sync()

    # Verify second incident is open
    inc2 = Incident.objects.exclude(pk=inc1.pk).get(control__slug="alpha")
    assert inc2.date_end is None

    # 4. Resolve the failure again
    KeyValue.objects.filter(key="alpha").delete()
    runner2.run_and_sync()

    # Verify second incident is closed
    inc2.refresh_from_db()
    assert inc2.date_end is not None
    assert inc2.date_end >= first_date_end

    # Crucial check: older closed incident's end date has NOT been altered
    inc1.refresh_from_db()
    assert inc1.date_end == first_date_end


def test_sync_logic_with_database_control(db_registry: ControlRegistry) -> None:
    """run_and_sync requires whealth.database to pass."""
    runner = db_registry.get_runner()

    # Mocking the database control result as success
    runner.results[("whealth", "database")] = []

    # We trigger run_and_sync which will now proceed to sync because of our mock
    # (Even if _run() itself blocks everything, we just want to see if the sync
    # logic executes)
    runner.run_and_sync()

    # If it reached here without crashing, it means the sync logic was entered
    # and the hostname/cli/results were saved to RunRecord.
    from whealth.models import RunRecord

    assert RunRecord.objects.count() > 0
