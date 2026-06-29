"""Tests for get_control_routes route building."""

from __future__ import annotations

from whealth.base import BaseControl
from whealth.registry import ControlInfo, ControlRegistry, Manifest


class FakeControl(BaseControl):
    """Minimal control stub for tests."""

    def get_failures(self) -> list:  # noqa: D102
        return []


def _make_info(app_label: str, slug: str) -> ControlInfo:
    return ControlInfo(
        app_label=app_label,
        slug=slug,
        title=slug.title(),
        module=f"{app_label}.controls.{slug}",
        control_class=FakeControl,
        manifest=Manifest(depends_on=()),
        readme=f"# {slug.title()}",
    )


def _build(registry: ControlRegistry, **kwargs) -> dict:
    from whealth.management.commands.get_control_routes import build_control_routes

    return build_control_routes(registry, **kwargs)


def test_relative_urls() -> None:
    """Relative URLs have no base prefix."""
    registry = ControlRegistry()
    registry.register(_make_info("test", "foo"))
    registry.register(_make_info("test", "bar"))

    data = _build(registry, base_url="")

    assert data["global"]["recap"] == "/whealth/recap.html"
    assert data["global"]["control"] == "/whealth/control.json"
    assert data["per_control"]["test.foo"]["self"] == "/whealth/control/test/foo.json"
    assert data["per_control"]["test.foo"]["deep"] == (
        "/whealth/control/test/foo/deep.json"
    )
    assert data["service_restart"][""] == (
        "/whealth/should-restart/{service_name}.json"
    )


def test_absolute_urls() -> None:
    """Absolute URLs use the provided base URL."""
    registry = ControlRegistry()
    registry.register(_make_info("test", "foo"))

    data = _build(registry, base_url="http://example.com:8080")

    assert data["global"]["control"] == "http://example.com:8080/whealth/control.json"
    assert (
        data["per_control"]["test.foo"]["self"]
        == "http://example.com:8080/whealth/control/test/foo.json"
    )
    assert (
        data["service_restart"][""]
        == "http://example.com:8080/whealth/should-restart/{service_name}.json"
    )


def test_urljoin_trailing_slash() -> None:
    """Trailing slash on base URL is handled correctly."""
    registry = ControlRegistry()
    registry.register(_make_info("test", "foo"))

    data = _build(registry, base_url="https://example.com/")
    assert data["global"]["recap"] == "https://example.com/whealth/recap.html"


def test_service_keys() -> None:
    """--service adds concrete keys to service_restart."""
    registry = ControlRegistry()
    registry.register(_make_info("test", "foo"))

    data = _build(registry, base_url="", services=("nginx", "postgres"))

    assert data["service_restart"][""] == "/whealth/should-restart/{service_name}.json"
    assert data["service_restart"]["nginx"] == "/whealth/should-restart/nginx.json"
    assert data["service_restart"]["postgres"] == (
        "/whealth/should-restart/postgres.json"
    )
    assert len(data["service_restart"]) == 3


def test_no_controls() -> None:
    """An empty registry produces an empty per_control dict."""
    registry = ControlRegistry()
    data = _build(registry, base_url="")
    assert data["per_control"] == {}
    assert data["global"]["recap"] == "/whealth/recap.html"


def test_none_base_url_is_relative() -> None:
    """When base_url is None, outputs relative URLs (same as empty string)."""
    registry = ControlRegistry()
    registry.register(_make_info("test", "foo"))

    data = _build(registry, base_url=None)

    assert data["global"]["control"] == "/whealth/control.json"
