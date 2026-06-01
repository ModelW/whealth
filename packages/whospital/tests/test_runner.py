"""Tests for the control runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from django.utils.timezone import now as django_now
from whealth.base import Failure
from whealth.models import Incident
from whealth.registry import ControlInfo, ControlRegistry, Manifest
from whospital_apps.models import KeyValue

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
    KeyValue.objects.update_or_create(key=key, defaults={"value": value})


# ---------------------------------------------------------------------------
# Basic: all pass
# ---------------------------------------------------------------------------


def test_all_pass(runner: ControlRunner) -> None:
    """All controls pass when no KeyValue entries are set."""
    runner.run()

    for slug in ("alpha", "beta", "gamma", "delta", "epsilon"):
        result = runner.results[("whospital_apps", slug)]
        assert result is not False
        assert result == []


# ---------------------------------------------------------------------------
# Error propagation: alpha errors -> all blocked
# ---------------------------------------------------------------------------


def test_alpha_error_blocks_all(runner: ControlRunner) -> None:
    """An error on alpha blocks everyone (they all depend transitively)."""
    _kv("alpha", "error")
    runner.run()

    result_alpha = runner.results[("whospital_apps", "alpha")]
    assert result_alpha is not False
    assert len(result_alpha) == 1
    assert result_alpha[0].outcome == "error"

    for slug in ("beta", "gamma", "delta", "epsilon"):
        assert runner.results[("whospital_apps", slug)] is False


# ---------------------------------------------------------------------------
# Warning does not block
# ---------------------------------------------------------------------------


def test_warning_does_not_block(runner: ControlRunner) -> None:
    """A warning on alpha still allows dependents to run."""
    _kv("alpha", "warning")
    runner.run()

    result_alpha = runner.results[("whospital_apps", "alpha")]
    assert result_alpha is not False
    assert len(result_alpha) == 1
    assert result_alpha[0].outcome == "warning"

    for slug in ("beta", "gamma", "delta", "epsilon"):
        result = runner.results[("whospital_apps", slug)]
        assert result is not False


# ---------------------------------------------------------------------------
# Error at mid-chain: beta errors -> gamma and epsilon blocked
# ---------------------------------------------------------------------------


def test_beta_error_blocks_downstream(runner: ControlRunner) -> None:
    """An error on beta blocks gamma and epsilon but not alpha or delta."""
    _kv("beta", "error")
    runner.run()

    # alpha and delta are independent of beta
    assert runner.results[("whospital_apps", "alpha")] is not False
    assert runner.results[("whospital_apps", "delta")] is not False

    # beta has an error
    result_beta = runner.results[("whospital_apps", "beta")]
    assert result_beta is not False
    assert len(result_beta) == 1
    assert result_beta[0].outcome == "error"

    # gamma depends on beta, epsilon depends on both delta and beta
    assert runner.results[("whospital_apps", "gamma")] is False
    assert runner.results[("whospital_apps", "epsilon")] is False


# ---------------------------------------------------------------------------
# Internal error at delta -> only epsilon blocked
# ---------------------------------------------------------------------------


def test_delta_internal_error_blocks_epsilon(runner: ControlRunner) -> None:
    """An internal_error on delta blocks epsilon but not alpha/beta/gamma."""
    _kv("delta", "internal_error")
    runner.run()

    assert runner.results[("whospital_apps", "alpha")] is not False
    assert runner.results[("whospital_apps", "beta")] is not False
    assert runner.results[("whospital_apps", "gamma")] is not False

    result_delta = runner.results[("whospital_apps", "delta")]
    assert result_delta is not False
    assert len(result_delta) == 1
    assert result_delta[0].outcome == "internal_error"

    # epsilon depends on delta - delta has internal_error -> blocked
    assert runner.results[("whospital_apps", "epsilon")] is False


# ---------------------------------------------------------------------------
# Exception in get_failures -> internal_error
# ---------------------------------------------------------------------------


def test_exception_in_control_produces_internal_error(
    runner: ControlRunner,
) -> None:
    """An exception raised by a control is caught and recorded."""
    _kv("alpha", "value_that_makes_utils_raise")
    runner.run()

    result = runner.results[("whospital_apps", "alpha")]
    assert result is not False
    assert len(result) == 1
    assert result[0].outcome == "internal_error"


# ---------------------------------------------------------------------------
# No controls registered
# ---------------------------------------------------------------------------


def test_empty_registry() -> None:
    """A runner with an empty registry produces no results."""
    runner = ControlRegistry().get_runner()
    runner.run()
    assert runner.results == {}


# ---------------------------------------------------------------------------
# Topological order: dependencies run before dependents
# ---------------------------------------------------------------------------


def test_topological_order(runner: ControlRunner) -> None:
    """Controls are run in dependency order (parents before children)."""
    runner.run()
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
    runner = db_registry.get_runner()
    runner.run_and_sync()
    assert Incident.objects.count() == 0
    assert all(isinstance(v, list) for v in runner.results.values())


def test_error_failure_creates_incident(db_registry: ControlRegistry) -> None:
    """An error on alpha creates an open incident."""
    _kv("alpha", "error")
    runner = db_registry.get_runner()
    runner.run_and_sync()

    incidents = Incident.objects.filter(control__slug="alpha")
    assert incidents.count() == 1
    inc = incidents.get()
    assert inc.key == "alpha"
    assert inc.date_start is not None
    assert inc.date_end is None
    assert inc.date_ignored is None


def test_multiple_failures_create_separate_incidents(
    db_registry: ControlRegistry,
) -> None:
    """A control with multiple failure keys creates one incident per key."""
    _kv("beta", "error")
    runner = db_registry.get_runner()
    runner.run_and_sync()

    incidents = Incident.objects.filter(control__slug="beta")
    assert incidents.count() == 1
    assert incidents.get().key == "beta"


def test_blocked_controls_dont_create_incidents(
    db_registry: ControlRegistry,
) -> None:
    """Controls that were blocked (False result) don't get incidents."""
    _kv("alpha", "error")
    runner = db_registry.get_runner()
    runner.run_and_sync()

    assert Incident.objects.filter(control__slug="alpha").count() == 1
    for slug in ("beta", "gamma", "delta", "epsilon"):
        assert Incident.objects.filter(control__slug=slug).count() == 0


def test_resolved_failure_closes_incident(db_registry: ControlRegistry) -> None:
    """A previously failing control that passes closes the incident."""
    _kv("alpha", "error")
    runner = db_registry.get_runner()
    runner.run_and_sync()
    assert (
        Incident.objects.filter(control__slug="alpha", date_end__isnull=True).count()
        == 1
    )

    KeyValue.objects.filter(key="alpha").delete()
    runner.run_and_sync()

    inc = Incident.objects.get(control__slug="alpha")
    assert inc.date_end is not None


def test_sync_does_not_close_blocked_incidents(
    db_registry: ControlRegistry,
) -> None:
    """Incidents stay open even when a control is blocked."""
    _kv("beta", "error")
    runner = db_registry.get_runner()
    runner.run_and_sync()

    _kv("gamma", "error")
    runner.run_and_sync()

    beta_inc = Incident.objects.get(control__slug="beta")
    assert beta_inc.date_end is None
    assert Incident.objects.filter(control__slug="gamma").count() == 0


def test_date_ignored_field_exists() -> None:
    """date_ignored field is nullable and defaults to None."""
    from whealth.models import Control

    control = Control.objects.create(slug="test-ctrl", title="Test", app_label="test")
    inc = Incident.objects.create(
        control=control,
        key="test-key",
        date_start=django_now(),
    )
    assert inc.date_ignored is None
    inc.date_ignored = django_now()
    inc.save()
    inc.refresh_from_db()
    assert inc.date_ignored is not None


# ---------------------------------------------------------------------------
# Sentry auto-detection / capture_exception
# ---------------------------------------------------------------------------


def test_capture_exception_noop_when_no_sentry() -> None:
    """capture_exception returns None when sentry-sdk is not installed."""
    from whealth.auto_sentry import capture_exception

    result = capture_exception(ValueError("test"))
    assert result is None


def test_control_exception_is_captured(
    monkeypatch: pytest.MonkeyPatch,
    registry: ControlRegistry,
) -> None:
    """An exception in a control is forwarded to capture_exception."""
    calls: list[BaseException] = []

    monkeypatch.setattr(
        "whealth.runner.capture_exception",
        lambda error=None, **kw: calls.append(error),
    )

    _kv("alpha", "value_that_makes_utils_raise")
    registry.sync_to_db()
    runner = registry.get_runner()
    runner.run()

    assert len(calls) == 1
    assert isinstance(calls[0], ValueError)


def test_sync_incidents_handles_db_error(
    monkeypatch: pytest.MonkeyPatch,
    registry: ControlRegistry,
) -> None:
    """A DB failure in sync_incidents is captured and does not crash."""
    calls: list[BaseException] = []

    monkeypatch.setattr(
        "whealth.runner._build_failure_map",
        lambda _r, _reg: (_ for _ in ()).throw(RuntimeError("db down")),
    )
    monkeypatch.setattr(
        "whealth.runner.capture_exception",
        lambda e, **kw: calls.append(e),  # type: ignore[arg-type]
    )

    runner = registry.get_runner()
    runner.run()
    runner.sync_incidents()

    assert len(calls) == 1
    assert isinstance(calls[0], RuntimeError)


# ---------------------------------------------------------------------------
# Failure context is persisted
# ---------------------------------------------------------------------------


def test_failure_context_saved_on_incident(
    db_registry: ControlRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure's context is stored in the incident record."""
    expected_context = {"message": "something broke", "code": 42}

    alpha_ctrl = db_registry.controllers[("whospital_apps", "alpha")]
    monkeypatch.setattr(
        alpha_ctrl._instance,
        "get_failures",
        lambda: [Failure(key="alpha", outcome="error", context=expected_context)],
    )

    runner = db_registry.get_runner()
    runner.run_and_sync()

    inc = Incident.objects.get(control__slug="alpha")
    assert inc.context == expected_context


def test_failure_context_updated_on_existing_incident(
    db_registry: ControlRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a failure's context changes, the existing incident is updated."""
    alpha_ctrl = db_registry.controllers[("whospital_apps", "alpha")]
    monkeypatch.setattr(
        alpha_ctrl._instance,
        "get_failures",
        lambda: [Failure(key="alpha", outcome="error", context={"v": 1})],
    )

    runner = db_registry.get_runner()
    runner.run_and_sync()

    inc = Incident.objects.get(control__slug="alpha")
    assert inc.context == {"v": 1}

    monkeypatch.setattr(
        alpha_ctrl._instance,
        "get_failures",
        lambda: [Failure(key="alpha", outcome="error", context={"v": 2})],
    )

    runner.run_and_sync()

    inc.refresh_from_db()
    assert inc.context == {"v": 2}


def test_failure_none_context_defaults_to_empty_dict(
    db_registry: ControlRegistry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failure with None context stores an empty dict."""
    alpha_ctrl = db_registry.controllers[("whospital_apps", "alpha")]
    monkeypatch.setattr(
        alpha_ctrl._instance,
        "get_failures",
        lambda: [Failure(key="alpha", outcome="error", context=None)],
    )

    runner = db_registry.get_runner()
    runner.run_and_sync()

    inc = Incident.objects.get(control__slug="alpha")
    assert inc.context == {}
