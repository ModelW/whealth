"""Registry for discovering and validating health controls."""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from django.apps import apps

from whealth.base import BaseControl, Failure

if TYPE_CHECKING:
    from whealth.graph import DependencyNote


@dataclasses.dataclass(frozen=True)
class ControlInfo:
    """Validated information about a discovered control."""

    app_label: str
    slug: str
    module: str
    control_class: type[BaseControl]
    manifest: Manifest
    readme: str
    title: str | None = None


@dataclasses.dataclass(frozen=True)
class Controller:
    """Wraps a :class:`ControlInfo` with an instantiated control.

    Proxies the :meth:`get_failures` call to the underlying control
    instance.  Equality and hashing are based on ``(app_label, slug)``.
    """

    info: ControlInfo
    _instance: BaseControl = dataclasses.field(init=False)

    def __post_init__(self) -> None:
        """Instantiate the control class after frozen init."""
        object.__setattr__(self, "_instance", self.info.control_class())

    @property
    def app_label(self) -> str:
        """App label of the wrapped control."""
        return self.info.app_label

    @property
    def slug(self) -> str:
        """Slug of the wrapped control."""
        return self.info.slug

    @property
    def title(self) -> str:
        """Title of the wrapped control, falling back to slug."""
        return self.info.title or self.info.slug

    @property
    def depends_on(self) -> list[tuple[str, str]]:
        """Resolved dependency keys ``(app_label, slug)``."""
        deps: list[tuple[str, str]] = []
        for raw in self.info.manifest.depends_on:
            if "." in raw:
                app, _, slug = raw.partition(".")
                deps.append((app, slug))
            else:
                deps.append((self.app_label, raw))
        return deps

    @property
    def key(self) -> tuple[str, str]:
        """Tuple identifier ``(app_label, slug)``."""
        return (self.info.app_label, self.info.slug)

    def __hash__(self) -> int:
        """Hash based on key."""
        return hash(self.key)

    def __eq__(self, other: object) -> bool:
        """Equality based on key."""
        if not isinstance(other, Controller):
            return NotImplemented
        return self.key == other.key

    def get_failures(self) -> list[Failure]:
        """Proxy to the underlying control instance."""
        return self._instance.get_failures()


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

    return ControlInfo(
        app_label=app_label,
        slug=slug,
        title=manifest.title,
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


@dataclasses.dataclass(frozen=True)
class DiscoveryResult:
    """Outcome of a full discovery pass."""

    errors: tuple[str, ...] = ()
    notes: tuple[DependencyNote, ...] = ()


@dataclasses.dataclass
class ControlRegistry:
    """Registry that discovers and validates health controls.

    Manages :class:`Controller` instances wrapping discovered controls.
    """

    controllers: dict[tuple[str, str], Controller] = dataclasses.field(
        default_factory=dict, init=False
    )
    discovery: DiscoveryResult | None = dataclasses.field(default=None, init=False)

    def register(self, info: ControlInfo) -> Controller:
        """Register a :class:`ControlInfo` and return its :class:`Controller`.

        The controller wraps a fresh instance of the control class and
        can be retrieved later via its ``key``.

        Raises
        ------
        KeyError
            If a controller with the same key is already registered.
        """
        controller = Controller(info=info)
        if controller.key in self.controllers:
            msg = f"Controller {controller.key!r} is already registered"
            raise KeyError(msg)
        self.controllers[controller.key] = controller
        return controller

    def get(self, app_label: str, slug: str) -> Controller | None:
        """Retrieve a previously registered controller by its key."""
        return self.controllers.get((app_label, slug))

    def discover(
        self,
    ) -> tuple[list[str], list[DependencyNote]]:
        """Discover, validate, and register all controls.

        Scans every installed Django app for ``controls/`` directories,
        loads valid controls, resolves their dependency graph, and
        registers each resulting :class:`Controller`.

        Returns
        -------
        tuple of (list[str], list[DependencyNote])
            A tuple of:
            - error messages from invalid controls or failed loads
            - dependency notes from the graph resolution pass
        """
        from whealth.graph import resolve_dependencies

        errors: list[str] = []
        candidates = list_potential_controls()
        loaded = list_controls(candidates)

        valid: list[ControlInfo] = []
        for r in loaded:
            if isinstance(r, ControlInfo):
                valid.append(r)
            else:
                errors.append(r)

        safe_controls, notes = resolve_dependencies(valid)

        for c in safe_controls:
            self.register(c)

        self.discovery = DiscoveryResult(errors=tuple(errors), notes=tuple(notes))
        return errors, notes

    def get_runner(self):
        """Return a :class:`ControlRunner` bound to this registry."""
        from whealth.runner import ControlRunner

        return ControlRunner(registry=self)

    def sync_to_db(self) -> None:
        """Reflect the current set of discovered controllers into the DB.

        Creates or updates :class:`~whealth.models.Control` rows for every
        registered controller using bulk operations.  Rows for controls that
        are no longer discovered are deactivated.

        The method issues at most 6 queries: one read, one bulk-create,
        one bulk-update (scalars), two for activity, plus clear-and-replace
        for depends_on links.
        """
        from whealth.models import Control as ControlModel

        known_slugs = {c.slug for c in self.controllers.values()}
        existing = {
            row.slug: row for row in ControlModel.objects.filter(slug__in=known_slugs)
        }

        self._sync_scalars(existing, known_slugs)
        self._sync_activity(known_slugs)
        self._sync_depends_on(known_slugs)

    def _sync_scalars(
        self,
        existing: dict[str, Any],
        known_slugs: set[str],
    ) -> None:
        """Bulk-create new rows and bulk-update changed scalar fields."""
        from whealth.models import Control as ControlModel

        scalar_updates: list[ControlModel] = []
        creates: list[ControlModel] = []

        for controller in self.controllers.values():
            slug = controller.slug
            if slug not in known_slugs:
                continue
            if slug in existing:
                row = existing[slug]
                dirty = False
                title = controller.title
                app_label = controller.app_label
                description = controller.info.readme
                if row.title != title:
                    row.title = title
                    dirty = True
                if row.app_label != app_label:
                    row.app_label = app_label
                    dirty = True
                if row.description != description:
                    row.description = description
                    dirty = True
                if dirty:
                    scalar_updates.append(row)
            else:
                creates.append(
                    ControlModel(
                        slug=slug,
                        title=controller.title,
                        app_label=controller.app_label,
                        description=controller.info.readme,
                        active=True,
                    )
                )

        if creates:
            ControlModel.objects.bulk_create(creates)
        if scalar_updates:
            ControlModel.objects.bulk_update(
                scalar_updates, ("title", "app_label", "description")
            )

    def _sync_activity(
        self,
        known_slugs: set[str],
    ) -> None:
        """Activate discovered rows and deactivate stale rows."""
        from whealth.models import Control as ControlModel

        ControlModel.objects.filter(slug__in=known_slugs, active=False).update(
            active=True
        )
        ControlModel.objects.exclude(slug__in=known_slugs).filter(active=True).update(
            active=False
        )

    def _sync_depends_on(
        self,
        known_slugs: set[str],
    ) -> None:
        """Clear and bulk-replace all depends_on links."""
        from whealth.models import Control as ControlModel

        if not known_slugs:
            return

        all_rows = {
            r.slug: r for r in ControlModel.objects.filter(slug__in=known_slugs)
        }

        through = ControlModel.depends_on.through

        pks = {r.pk for r in all_rows.values()}
        through.objects.filter(from_control_id__in=pks).delete()

        links: list[Any] = []
        for controller in self.controllers.values():
            if controller.slug not in known_slugs:
                continue
            parent = all_rows.get(controller.slug)
            if parent is None:
                continue
            for _app_label, dep_slug in controller.depends_on:
                dep = all_rows.get(dep_slug)
                if dep is not None:
                    links.append(
                        through(
                            from_control_id=parent.pk,
                            to_control_id=dep.pk,
                        )
                    )

        if links:
            through.objects.bulk_create(links, ignore_conflicts=True)


_cr_lock = threading.Lock()
_cr: ControlRegistry | None = None


def get_control_registry() -> ControlRegistry:
    """Return the singleton ``ControlRegistry``, discovering controls on first call."""
    global _cr

    if _cr is None:
        with _cr_lock:
            if _cr is None:
                _cr = ControlRegistry()
                _cr.discover()

    return _cr
