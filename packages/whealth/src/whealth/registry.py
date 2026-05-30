"""Registry for discovering and validating health controls."""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import threading
from pathlib import Path

import yaml
from django.apps import apps

from whealth.base import BaseControl


@dataclasses.dataclass(frozen=True)
class ControlInfo:
    """Validated information about a discovered control."""

    app_label: str
    slug: str
    title: str
    module: str
    control_class: type[BaseControl]
    manifest: Manifest
    readme: str


@dataclasses.dataclass(frozen=True)
class Manifest:
    """Parsed ``manifest.yaml`` for a control."""

    depends_on: tuple[str, ...]
    title: str | None = None


@dataclasses.dataclass(frozen=True)
class _Candidate:
    """Internal struct representing a potential control found on disk."""

    app_label: str
    module_name: str
    slug: str


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_file(path: Path) -> str | None:
    """Read a file, returning ``None`` if it cannot be read."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _parse_yaml(text: str) -> dict[str, object] | None:
    """Parse YAML text, returning ``None`` on failure."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    return data


def _import_control_module(
    module: str,
) -> tuple[object, Path] | str:
    """Import *module* and return the module object and its parent directory."""
    try:
        mod = importlib.import_module(module)
    except ImportError as exc:
        return f"Cannot import module {module!r}: {exc}"
    mod_path = getattr(mod, "__file__", None)
    if mod_path is None:
        return f"Module {module!r} has no __file__ (namespace package?)."
    return mod, Path(mod_path).resolve().parent


def _extract_control_class(
    mod: object,
    module: str,
) -> type[BaseControl] | str:
    """Find exactly one BaseControl subclass in *mod*."""
    candidates: list[type[BaseControl]] = []
    for _, obj in inspect.getmembers(mod):
        if (
            inspect.isclass(obj)
            and issubclass(obj, BaseControl)
            and obj is not BaseControl
        ):
            candidates.append(obj)
    match candidates:
        case [single]:
            return single
        case []:
            return f"Module {module!r} contains no BaseControl subclass."
        case _:
            return (
                f"Module {module!r} contains multiple BaseControl "
                f"subclasses ({len(candidates)}), expected exactly one."
            )


def _validate_manifest(pkg_dir: Path, module: str) -> Manifest | str:
    """Read and validate the YAML manifest for a control."""
    raw = _read_file(pkg_dir / "manifest.yaml")
    if raw is None:
        return f"Control {module!r} is missing manifest.yaml."
    manifest = _parse_yaml(raw)
    if manifest is None:
        return f"Control {module!r} has an invalid or empty manifest.yaml."
    match manifest:
        case {"depends_on": list(deps), **extra}:
            if not all(isinstance(d, str) for d in deps):
                return (
                    f"Control {module!r} manifest.yaml 'depends_on' "
                    f"contains non-string entries."
                )
            title: str | None = None
            match extra.get("title"):
                case str(t):
                    title = t
                case _:
                    pass
            return Manifest(depends_on=tuple(deps), title=title)
        case _:
            return (
                f"Control {module!r} manifest.yaml must contain a "
                f"'depends_on' key with a list of strings."
            )


def _validate_readme_text(pkg_dir: Path, module: str) -> str | None:
    """Read the README for a control."""
    return _read_file(pkg_dir / "README.md")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_potential_controls() -> list[_Candidate]:
    """Discover all control directories across installed Django apps."""
    result: list[_Candidate] = []
    for config in apps.get_app_configs():
        controls_dir = Path(config.path) / "controls"
        if not controls_dir.is_dir():
            continue
        for entry in sorted(controls_dir.iterdir()):
            if entry.is_dir() and not entry.name.startswith("_"):
                result.append(
                    _Candidate(
                        app_label=config.label,
                        module_name=config.name,
                        slug=entry.name,
                    )
                )
    return result


def attempt_load(
    module: str,
    app_label: str,
) -> ControlInfo | str:
    """Try to load a control from the given module path.

    A valid control must contain exactly one subclass of
    :class:`~whealth.base.BaseControl`, a YAML ``manifest.yaml``, and a
    Markdown ``README.md``. Any missing or invalid piece produces a
    descriptive error string instead of crashing.

    Parameters
    ----------
    module : str
        Dotted Python module path to the control package, e.g.
        ``"whealth.controls.database"``.
    app_label : str
        Django app label this control belongs to.

    Returns
    -------
    ControlInfo or str
        A :class:`ControlInfo` if the control is valid, or a string
        explaining what is wrong.
    """
    slug = module.rpartition(".")[2]

    imported = _import_control_module(module)
    if isinstance(imported, str):
        return imported
    mod, pkg_dir = imported

    control_cls = _extract_control_class(mod, module)
    if isinstance(control_cls, str):
        return control_cls

    manifest = _validate_manifest(pkg_dir, module)
    if isinstance(manifest, str):
        return manifest

    readme = _validate_readme_text(pkg_dir, module)
    if readme is None:
        return f"Control {module!r} is missing README.md."

    title = manifest.title or slug
    return ControlInfo(
        app_label=app_label,
        slug=slug,
        title=title,
        module=module,
        control_class=control_cls,
        manifest=manifest,
        readme=readme,
    )


def list_controls(
    candidates: list[_Candidate],
) -> list[ControlInfo | str]:
    """Load all valid controls from the given candidate list.

    Parameters
    ----------
    candidates : list of _Candidate
        Output from :func:`list_potential_controls`.

    Returns
    -------
    list of ControlInfo or str
        One entry per candidate, in the same order.
    """
    results: list[ControlInfo | str] = []
    for c in candidates:
        module = f"{c.module_name}.controls.{c.slug}"
        results.append(attempt_load(module, app_label=c.app_label))
    return results


class ControlRegistry:
    """Registry that discovers and validates health controls.

    For now this is an empty placeholder — the real logic lives in
    module-level functions. This class exists so that a future version
    can hold shared state (caches, config, etc.) while keeping a stable
    public API via :func:`get_control_registry`.
    """


_cr_lock = threading.Lock()
_cr: ControlRegistry | None = None


def get_control_registry() -> ControlRegistry:
    """Return the singleton ``ControlRegistry``."""
    global _cr

    if _cr is None:
        with _cr_lock:
            if _cr is None:
                _cr = ControlRegistry()

    return _cr
