"""Admin configuration for whealth."""

# mypy: ignore-errors

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.shortcuts import get_object_or_404, redirect
from django.urls import path as url_path
from django.urls import reverse
from django.utils.timezone import now as django_now
from django.utils.translation import gettext_lazy as _

from whealth.models import Control, Cron, Incident, RunRecord

if TYPE_CHECKING:
    from django.http import HttpRequest


class StatusFilter(SimpleListFilter):
    """Filter incidents by active, resolved, or ignored state."""

    title = _("status")
    parameter_name = "status"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        """Return the filter options."""
        return [
            ("active", _("Active")),
            ("resolved", _("Resolved")),
            ("ignored", _("Ignored")),
        ]

    def queryset(self, request: HttpRequest, queryset: Any) -> Any:
        """Apply the selected filter."""
        match self.value():
            case "active":
                return queryset.filter(date_end__isnull=True, date_ignored__isnull=True)
            case "resolved":
                return queryset.filter(date_end__isnull=False)
            case "ignored":
                return queryset.filter(
                    date_end__isnull=True, date_ignored__isnull=False
                )
        return queryset


@admin.register(Incident)
class IncidentAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin interface for incidents."""

    list_display: ClassVar = (
        "control",
        "key",
        "status",
        "date_start",
        "date_end",
        "date_ignored",
    )
    list_filter: ClassVar = (
        StatusFilter,
        "control",
    )
    search_fields: ClassVar = (
        "control__slug",
        "control__title",
        "key",
    )
    readonly_fields: ClassVar = (
        "control",
        "key",
        "status",
        "context",
        "date_start",
        "date_end",
        "date_ignored",
    )
    actions: ClassVar = ["ignore_selected"]
    date_hierarchy = "date_start"

    fieldsets: ClassVar = [
        (
            None,
            {
                "fields": (
                    "control",
                    "key",
                    "status",
                ),
            },
        ),
        (
            _("Timeline"),
            {
                "fields": (
                    "date_start",
                    "date_end",
                    "date_ignored",
                ),
            },
        ),
        (
            _("Context"),
            {
                "classes": ("collapse",),
                "fields": ("context",),
            },
        ),
    ]

    def get_urls(self) -> list[str]:
        """Add the custom ignore-incident endpoint."""
        urls = super().get_urls()
        custom = [
            url_path(
                "<int:incident_id>/ignore/",
                self.admin_site.admin_view(self.ignore_view),
                name="whealth_incident_ignore",
            ),
        ]
        return custom + urls

    def get_queryset(self, request):  # type: ignore[no-untyped-def]
        """Select related control for display efficiency."""
        return super().get_queryset(request).select_related("control")

    @admin.display(description=_("status"))
    def status(self, obj: Incident) -> str:
        """Render a human-readable status for the incident."""
        if obj.date_end and obj.date_ignored:
            return _("ignored and resolved")
        if obj.date_end:
            return _("resolved")
        if obj.date_ignored:
            return _("ignored")
        return _("active")

    @admin.action(description=_("Ignore selected incidents"))
    def ignore_selected(self, request, queryset):  # type: ignore[no-untyped-def]
        """Silence active incidents by setting date_ignored."""
        updated = queryset.filter(date_end__isnull=True).update(
            date_ignored=django_now()
        )
        self.message_user(
            request,
            _("Ignored %(count)d active incident(s).") % {"count": updated},
            messages.SUCCESS,
        )

    def ignore_view(self, request, incident_id):  # type: ignore[no-untyped-def]
        """Ignore a single incident and redirect back to the change page."""
        inc = get_object_or_404(Incident, pk=incident_id)
        if inc.date_end is None:
            Incident.objects.filter(pk=incident_id).update(date_ignored=django_now())
            self.message_user(
                request,
                _("Incident %(incident)s ignored.") % {"incident": inc},
                messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                _("Cannot ignore a resolved incident."),
                messages.WARNING,
            )
        return redirect(reverse("admin:whealth_incident_change", args=[incident_id]))

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        """Incidents are created programmatically, not manually."""
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Incidents are read-only in the admin."""
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Incidents are read-only in the admin."""
        return False


@admin.register(Control)
class ControlAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin interface for controls."""

    list_display: ClassVar = (
        "slug",
        "title",
        "app_label",
        "active",
    )
    list_filter: ClassVar = ("active", "app_label")
    search_fields: ClassVar = ("slug", "title")
    readonly_fields: ClassVar = ("slug", "title", "app_label", "description", "active")

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        """Return False — controls are created by discovery."""
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Return False — controls are read-only in the admin."""
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Return False — controls are managed by discovery."""
        return False


@admin.register(Cron)
class CronAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin interface for cron checks."""

    list_display: ClassVar = (
        "slug",
        "schedule",
        "schedule_type",
        "timezone",
        "checkin_margin",
        "max_runtime",
    )
    search_fields: ClassVar = ("slug",)

    def has_add_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Return False — crons are managed programmatically."""
        return False

    def has_change_permission(self, request, obj=...):
        """Crons are read-only in the admin."""
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Return False — crons are managed programmatically."""
        return False


@admin.register(RunRecord)
class RunRecordAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin interface for run records."""

    list_display: ClassVar = (
        "date_start",
        "hostname",
        "cli",
        "summary_display",
        "duration_display",
    )
    list_filter: ClassVar = ("hostname",)
    date_hierarchy = "date_start"
    readonly_fields: ClassVar = (
        "date_start",
        "date_end",
        "hostname",
        "cli",
        "results",
    )

    fieldsets: ClassVar = [
        (
            None,
            {
                "fields": (
                    "date_start",
                    "date_end",
                    "hostname",
                    "cli",
                ),
            },
        ),
        (
            _("Results"),
            {
                "fields": ("results",),
            },
        ),
    ]

    @admin.display(description=_("summary"))
    def summary_display(self, obj: RunRecord) -> str:
        """Render a compact summary string."""
        r = obj.results
        if not r:
            return "—"
        p = w = e = b = 0
        for v in r.values():
            if v is None:
                b += 1
            elif not v:
                p += 1
            elif any(f.get("outcome") in ("error", "internal_error") for f in v):
                e += 1
            elif any(f.get("outcome") == "warning" for f in v):
                w += 1
            else:
                p += 1
        parts = [f"{p}P"]
        if w:
            parts.append(f"{w}W")
        if e:
            parts.append(f"{e}E")
        if b:
            parts.append(f"{b}B")
        return "  ".join(parts)

    @admin.display(description=_("duration"))
    def duration_display(self, obj: RunRecord) -> str:
        """Render human-readable duration."""
        d = obj.duration
        if d is None:
            return "—"
        total = int(d.total_seconds())
        if total < 60:
            return f"{total}s"
        return f"{total // 60}m {total % 60}s"

    def has_add_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Return False — run records are created programmatically."""
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Run records are read-only in the admin."""
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """Run records are read-only in the admin."""
        return False
