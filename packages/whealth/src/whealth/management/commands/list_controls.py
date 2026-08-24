"""Management command to list all discovered controls."""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from whealth.graph import DependencyIssue
from whealth.registry import get_control_registry


class Command(BaseCommand):
    """List all available controls and validate their integrity."""

    help = _("List all available health controls.")

    def handle(self, *args: str, **options: str) -> str:
        """Execute the command."""
        registry = get_control_registry()
        if registry.discovery is None:
            msg = (
                "Control discovery has not been run yet. "
                "Make sure whealth.apps.WhealthConfig is in INSTALLED_APPS."
            )
            raise RuntimeError(msg)

        errors = list(registry.discovery.errors)
        notes = list(registry.discovery.notes)

        self.stdout.write(self.style.SQL_FIELD(_("=== Valid controls ===")))

        if not registry.controllers:
            self.stdout.write(_("  (none)"))

        for controller in registry.controllers.values():
            # Meta controls have no Python check of their own, which is
            # worth surfacing when eyeballing the registry.
            meta_marker = " (meta)" if controller.is_meta else ""
            self.stdout.write(
                f"  {self.style.SQL_FIELD(controller.title)} "
                f"({self.style.MIGRATE_LABEL(controller.app_label)}."
                f"{self.style.MIGRATE_LABEL(controller.slug)})"
                f"{meta_marker}"
            )

        self.stdout.write("")
        self.stdout.write(self.style.SQL_FIELD(_("=== Checklist ===")))

        has_issues = False

        if errors:
            has_issues = True
            count = len(errors)
            self.stdout.write(
                ngettext(
                    "  \u274c Detected %(count)d invalid control",
                    "  \u274c Detected %(count)d invalid controls",
                    count,
                )
                % {"count": count}
            )
            for e in errors:
                self.stdout.write(f"    \u274c {e}")
        else:
            self.stdout.write(_("  \u2705 All detected controls are valid"))

        if notes:
            has_issues = True
            count = len(notes)
            msg = ngettext(
                "  \u274c Found %(count)d problematic dependency",
                "  \u274c Found %(count)d problematic dependencies",
                count,
            ) % {"count": count}
            self.stdout.write(msg)
            for n in notes:
                ref = f"{n.control_app_label}.{n.control_slug}"
                if n.reason == DependencyIssue.CYCLE:
                    self.stdout.write(
                        _(
                            "    \u274c Removed dependency "
                            "'%(dep)s' from '%(ref)s' "
                            "(would create a loop)"
                        )
                        % {"dep": n.dependency_ref, "ref": ref}
                    )
                else:
                    self.stdout.write(
                        _(
                            "    \u274c Dependency '%(dep)s' in "
                            "'%(ref)s' points to an unknown control"
                        )
                        % {"dep": n.dependency_ref, "ref": ref}
                    )
        else:
            self.stdout.write(_("  \u2705 Dependencies form a consistent graph"))

        if has_issues:
            sys.exit(1)

        return ""
