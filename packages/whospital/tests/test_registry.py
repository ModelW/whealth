"""Tests for control discovery and validation."""

from __future__ import annotations

import sys
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from whealth.graph import resolve_dependencies
from whealth.registry import (
    ControlInfo,
    attempt_load,
    list_controls,
    list_potential_controls,
)


@pytest.fixture
def tmp_control(request: pytest.FixtureRequest, tmp_path: Path) -> str:
    """Create a temporary control module.

    Accepts ``manifest``, ``readme`` and ``control_class`` via
    ``@pytest.mark.control(...)``.

    Marker::

        @pytest.mark.control(
            manifest='...',
            readme='...',
        )

    Returns the dotted module path that can be passed to
    ``registry.attempt_load()``.
    """
    marker = request.node.get_closest_marker("control")
    if marker is None:
        pytest.fail("tmp_control fixture requires @pytest.mark.control(...)")

    slug = marker.kwargs.get("slug", request.node.name)
    manifest = marker.kwargs.get("manifest", "depends_on: []\n")
    readme = marker.kwargs.get("readme", "# {slug}\n")
    control_class = marker.kwargs.get(
        "control_class",
        dedent("""\
        from whealth import BaseControl


        class Control(BaseControl):
            \"\"\"A test control.\"\"\"

            def check(self) -> None:
                pass
        """),
    )

    pkg_dir = tmp_path / slug
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text(control_class)
    if manifest is not None:
        (pkg_dir / "manifest.yaml").write_text(manifest)
    if readme is not None:
        (pkg_dir / "README.md").write_text(readme)

    sys.path.insert(0, str(tmp_path))
    return slug


def test_valid_database_control() -> None:
    """Loading the built-in database control succeeds."""
    info = attempt_load(
        "whealth.controls.database",
        app_label="whealth",
    )
    assert info.module == "whealth.controls.database"
    assert info.app_label == "whealth"
    assert info.slug == "database"
    assert info.control_class.__name__ == "Control"
    assert info.manifest.depends_on == ()


def test_valid_bleeps_control() -> None:
    """Loading the cross-app bleeps control succeeds."""
    info = attempt_load(
        "whospital_apps.controls.bleeps",
        app_label="whospital_apps",
    )
    assert info.app_label == "whospital_apps"
    assert info.slug == "bleeps"
    assert info.manifest.depends_on == ("whealth.database",)


@pytest.mark.control(manifest="depends_on: []\n", readme="# fine\n")
def test_valid_tmp_control(tmp_control: str) -> None:
    """A minimally valid temp control loads successfully."""
    info = attempt_load(tmp_control, app_label="test")
    assert info.module == tmp_control
    assert info.manifest.depends_on == ()


def test_nonexistent_module() -> None:
    """A module that cannot be imported returns an error string."""
    error = attempt_load("whealth.controls.nope", app_label="whealth")
    assert "Cannot import module" in error


def test_module_without_control() -> None:
    """A module with no BaseControl subclass returns an error string."""
    error = attempt_load("whealth.base", app_label="whealth")
    assert "contains no BaseControl subclass" in error


@pytest.mark.control(manifest=None, readme="# fine\n")
def test_missing_manifest(tmp_control: str) -> None:
    """A control without manifest.yaml returns an error string."""
    error = attempt_load(tmp_control, app_label="test")
    assert "missing manifest.yaml" in error


@pytest.mark.control(manifest="", readme="# fine\n")
def test_empty_manifest(tmp_control: str) -> None:
    """A control with an empty manifest.yaml returns an error string."""
    error = attempt_load(tmp_control, app_label="test")
    assert "invalid or empty manifest.yaml" in error


@pytest.mark.control(manifest=": : : broken", readme="# fine\n")
def test_invalid_manifest(tmp_control: str) -> None:
    """A control with invalid YAML returns an error string."""
    error = attempt_load(tmp_control, app_label="test")
    assert "invalid or empty manifest.yaml" in error


@pytest.mark.control(manifest="foo: bar\n", readme="# fine\n")
def test_wrong_manifest_shape(tmp_control: str) -> None:
    """A manifest without a depends_on list returns an error string."""
    error = attempt_load(tmp_control, app_label="test")
    assert "must contain a 'depends_on' key" in error


@pytest.mark.control(manifest="depends_on:\n  - 42\n", readme="# fine\n")
def test_nonstring_depends_on(tmp_control: str) -> None:
    """A manifest with non-string depends_on entries returns an error."""
    error = attempt_load(tmp_control, app_label="test")
    assert "contains non-string entries" in error


@pytest.mark.control(manifest="depends_on: []\n", readme=None)
def test_missing_readme(tmp_control: str) -> None:
    """A control without README.md returns an error string."""
    error = attempt_load(tmp_control, app_label="test")
    assert "missing README.md" in error


def test_list_potential_controls() -> None:
    """Discover controls from all installed Django apps."""
    controls = list_potential_controls()
    entries = {(c.app_label, c.slug) for c in controls}
    assert ("whealth", "database") in entries
    assert ("whospital_apps", "bleeps") in entries


def test_list_controls() -> None:
    """Loading all valid controls returns one result per candidate."""
    candidates = list_potential_controls()
    results = list_controls(candidates)
    assert len(results) == len(candidates)
    slugs = {
        (r.app_label, r.slug)
        for r in results
        if isinstance(r, ControlInfo)
    }
    assert ("whealth", "database") in slugs
    assert ("whospital_apps", "bleeps") in slugs


def test_resolve_dependencies_no_cycle() -> None:
    """Controls without cycles pass through unchanged."""
    candidates = list_potential_controls()
    results = list_controls(candidates)
    valid = [r for r in results if isinstance(r, ControlInfo)]

    safe, dropped = resolve_dependencies(valid)
    assert len(safe) == len(valid)
    assert dropped == []


def test_resolve_dependencies_removes_cycle() -> None:
    """A cycle between two controls is broken by dropping one edge."""
    from whealth.base import BaseControl
    from whealth.registry import Manifest

    class FakeControl(BaseControl):
        def check(self) -> None:
            pass

    manifest_a = Manifest(depends_on=("b",))
    manifest_b = Manifest(depends_on=("a",))

    info_a = ControlInfo(
        app_label="test",
        slug="a",
        title="A",
        module="test.controls.a",
        control_class=FakeControl,
        manifest=manifest_a,
        readme="# A",
    )
    info_b = ControlInfo(
        app_label="test",
        slug="b",
        title="B",
        module="test.controls.b",
        control_class=FakeControl,
        manifest=manifest_b,
        readme="# B",
    )

    safe, dropped = resolve_dependencies([info_a, info_b])
    assert len(safe) == 2
    assert len(dropped) == 1


def test_resolve_dependencies_unresolved() -> None:
    """A dependency pointing to a non-existent control is reported."""
    from whealth.base import BaseControl
    from whealth.registry import Manifest

    class FakeControl(BaseControl):
        def check(self) -> None:
            pass

    manifest = Manifest(depends_on=("ghost",))
    info = ControlInfo(
        app_label="test",
        slug="a",
        title="A",
        module="test.controls.a",
        control_class=FakeControl,
        manifest=manifest,
        readme="# A",
    )

    safe, notes = resolve_dependencies([info])
    assert len(safe) == 1
    assert len(notes) == 1
    note = notes[0]
    assert note.reason.name == "UNRESOLVED"
    assert note.dependency_ref == "ghost"
    assert note.control_slug == "a"
    # An unresolved dependency is kept in safe depends_on
    # (it's not a cycle, just an unknown reference).
    assert safe[0].manifest.depends_on == ("ghost",)
