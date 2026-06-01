"""Management command to run all controls and sync results."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from whealth.auto_sentry import capture_exception
from whealth.registry import ControlRegistry, get_control_registry
from whealth.runner import ControlRunner, RunResult


def _render_result(
    slug: str,
    result: RunResult,
    style: Any,
) -> tuple[str, int]:
    """Render a single control's result line and return its severity.

    Returns
    -------
    tuple[str, int]
        The formatted output line and a numeric severity:
        0 = pass, 1 = warning, 2 = error, 3 = blocked.
    """
    if result is False:
        return f"  [{style.WARNING('BLOCKED')}] {slug}", 3

    if not result:
        return f"  [{style.SUCCESS('PASS')}] {slug}", 0

    warnings = [f.key for f in result if f.outcome == "warning"]
    errors = [f.key for f in result if f.outcome in ("error", "internal_error")]

    if errors and not warnings:
        label = style.ERROR("ERROR")
        detail = "/".join(errors)
        return f"  [{label}] {slug} ({detail})", 2
    if warnings and not errors:
        label = style.WARNING("WARN")
        detail = "/".join(warnings)
        return f"  [{label}] {slug} ({detail})", 1

    label = style.ERROR("ERROR")
    detail = "/".join(errors + warnings)
    return f"  [{label}] {slug} ({detail})", 2


def _count_results(
    results: dict[tuple[str, str], RunResult],
) -> tuple[int, int, int, int]:
    """Count pass/warning/error/blocked results."""
    p = w = e = b = 0
    for v in results.values():
        if v is False:
            b += 1
        elif not v:
            p += 1
        else:
            has_w = any(f.outcome == "warning" for f in v)
            has_e = any(f.outcome in ("error", "internal_error") for f in v)
            if has_e:
                e += 1
            elif has_w:
                w += 1
    return p, w, e, b


class Command(BaseCommand):
    """Run every discovered control and sync results to the database."""

    help = _("Run all health controls and sync results to the database.")

    def handle(self, *args: str, **options: str) -> str:
        """Execute the command."""
        registry = get_control_registry()
        if registry.discovery is None:
            msg = (
                "Control discovery has not been run yet. "
                "Make sure whealth.apps.WhealthConfig is in INSTALLED_APPS."
            )
            raise CommandError(msg)

        total = len(registry.controllers)
        if not total:
            self.stdout.write(self.style.WARNING(_("No controls discovered.")))
            return ""

        self.stdout.write(
            ngettext(
                "Running %(count)d control...",
                "Running %(count)d controls...",
                total,
            )
            % {"count": total}
        )

        try:
            registry.sync_to_db()
        except Exception as exc:
            capture_exception(exc)
            self.stdout.write(self.style.WARNING(_("  DB sync failed, continuing...")))

        runner = registry.get_runner()
        runner.run_and_sync()

        _write_results(runner, registry, self)
        return ""


def _write_results(
    runner: ControlRunner,
    registry: ControlRegistry,
    cmd: Command,
) -> None:
    """Write per-control results and summary to stdout."""
    for controller in registry.controllers.values():
        result = runner.results.get(controller.key)
        if result is None:
            continue
        line, _severity = _render_result(controller.slug, result, cmd.style)
        cmd.stdout.write(line)

    cmd.stdout.write("")
    p, w, e, b = _count_results(runner.results)
    parts = [f"{p} passed"]
    if w:
        parts.append(f"{w} warnings")
    if e:
        parts.append(f"{e} errors")
    if b:
        parts.append(f"{b} blocked")

    summary = ", ".join(parts)

    if e or b:
        cmd.stdout.write(cmd.style.ERROR(summary))
    elif w:
        cmd.stdout.write(cmd.style.WARNING(summary))
    else:
        cmd.stdout.write(cmd.style.SUCCESS(summary))
