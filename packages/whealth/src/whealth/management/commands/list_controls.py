"""Management command to list all discovered controls."""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from whealth.graph import DependencyIssue, resolve_dependencies
from whealth.registry import (
    ControlInfo,
    list_controls,
    list_potential_controls,
)


class Command(BaseCommand):
    """List all available controls and validate their integrity."""

    help = _("List all available health controls.")

    def _print_controls(
        self, results: list[ControlInfo | str]
    ) -> list[ControlInfo]:
        """Print valid controls and return them."""
        style_good = self.style.SQL_FIELD
        valid: list[ControlInfo] = []
        for r in results:
            if isinstance(r, ControlInfo):
                valid.append(r)
                self.stdout.write(
                    f"  {style_good(r.title)} "
                    f"({self.style.MIGRATE_LABEL(r.app_label)}."
                    f"{self.style.MIGRATE_LABEL(r.slug)})"
                )
        return valid

    def _check_section_ready(
        self, results: list[ControlInfo | str]
    ) -> bool:
        """Check all valid vs invalid controls."""
        rejected = [r for r in results if not isinstance(r, ControlInfo)]
        if rejected:
            count = len(rejected)
            self.stdout.write(
                ngettext(
                    "  \u274c Detected %(count)d invalid control",
                    "  \u274c Detected %(count)d invalid controls",
                    count,
                )
                % {"count": count}
            )
            for r in rejected:
                self.stdout.write(f"    \u274c {r}")
            return True
        self.stdout.write(_("  \u2705 All detected controls are valid"))
        return False

    def _check_section_deps(
        self, valid_controls: list[ControlInfo]
    ) -> bool:
        """Check dependency consistency. Returns True if issues found."""
        if not valid_controls:
            self.stdout.write(
                _("  \u2705 Dependencies form a consistent graph")
            )
            return False
        _safe_controls, notes = resolve_dependencies(valid_controls)
        if not notes:
            self.stdout.write(
                _("  \u2705 Dependencies form a consistent graph")
            )
            return False

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
        return True

    def handle(self, *args: str, **options: str) -> str:
        """Execute the command."""
        candidates = list_potential_controls()
        results = list_controls(candidates)

        self.stdout.write(
            self.style.SQL_FIELD(_("=== Valid controls ==="))
        )

        valid_controls = self._print_controls(results)

        if not valid_controls:
            self.stdout.write(_("  (none)"))

        self.stdout.write("")
        self.stdout.write(
            self.style.SQL_FIELD(_("=== Checklist ==="))
        )

        has_ready = self._check_section_ready(results)
        has_deps = self._check_section_deps(valid_controls)

        if has_ready or has_deps:
            sys.exit(1)

        return ""
