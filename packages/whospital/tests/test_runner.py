"""Tests for the control runner."""

from __future__ import annotations

import pytest
from whealth.registry import (
    ControlRegistry,
    get_control_registry,
)
from whealth.runner import ControlRunner
from whospital_apps.models import KeyValue

pytestmark = [pytest.mark.django_db]


@pytest.fixture(autouse=True)
def _clear_registry() -> None:
    """Reset the singleton registry before each test."""
    registry = get_control_registry()
    registry.controllers.clear()
    registry.discovery = None


def _kv(key: str, value: str) -> None:
    """Create or update a KeyValue entry."""
    KeyValue.objects.update_or_create(key=key, defaults={"value": value})


def _run() -> ControlRunner:
    """Discover and run all controls, returning the runner."""
    registry = get_control_registry()
    registry.discover()
    runner = ControlRunner(registry=registry)
    runner.run()
    return runner


# ---------------------------------------------------------------------------
# Basic: all pass
# ---------------------------------------------------------------------------


def test_all_pass() -> None:
    """All controls pass when no KeyValue entries are set."""
    runner = _run()

    for slug in ("alpha", "beta", "gamma", "delta", "epsilon"):
        result = runner.results[("whospital_apps", slug)]
        assert result is not False
        assert result == []


# ---------------------------------------------------------------------------
# Error propagation: alpha errors -> all blocked
# ---------------------------------------------------------------------------


def test_alpha_error_blocks_all() -> None:
    """An error on alpha blocks everyone (they all depend transitively)."""
    _kv("alpha", "error")
    runner = _run()

    result_alpha = runner.results[("whospital_apps", "alpha")]
    assert result_alpha is not False
    assert len(result_alpha) == 1
    assert result_alpha[0].outcome == "error"

    for slug in ("beta", "gamma", "delta", "epsilon"):
        assert runner.results[("whospital_apps", slug)] is False


# ---------------------------------------------------------------------------
# Warning does not block
# ---------------------------------------------------------------------------


def test_warning_does_not_block() -> None:
    """A warning on alpha still allows dependents to run."""
    _kv("alpha", "warning")
    runner = _run()

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


def test_beta_error_blocks_downstream() -> None:
    """An error on beta blocks gamma and epsilon but not alpha or delta."""
    _kv("beta", "error")
    runner = _run()

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


def test_delta_internal_error_blocks_epsilon() -> None:
    """An internal_error on delta blocks epsilon but not alpha/beta/gamma."""
    _kv("delta", "internal_error")
    runner = _run()

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


def test_exception_in_control_produces_internal_error() -> None:
    """An exception raised by a control is caught and recorded."""
    _kv("alpha", "value_that_makes_utils_raise")
    runner = _run()

    result = runner.results[("whospital_apps", "alpha")]
    assert result is not False
    assert len(result) == 1
    assert result[0].outcome == "internal_error"


# ---------------------------------------------------------------------------
# No controls registered
# ---------------------------------------------------------------------------


def test_empty_registry() -> None:
    """A runner with an empty registry produces no results."""
    registry = ControlRegistry()
    runner = ControlRunner(registry=registry)
    runner.run()
    assert runner.results == {}


# ---------------------------------------------------------------------------
# Topological order: dependencies run before dependents
# ---------------------------------------------------------------------------


def test_topological_order() -> None:
    """Controls are run in dependency order (parents before children)."""
    runner = _run()
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
