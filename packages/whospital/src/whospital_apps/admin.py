"""Admin configuration for whospital_apps."""

from __future__ import annotations

from django.contrib import admin

from whospital_apps.models import KeyValue


@admin.register(KeyValue)
class KeyValueAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin interface for KeyValue entries."""

    def has_add_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """KeyValue entries are managed programmatically."""
        return False

    def has_change_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """KeyValue entries are read-only in the admin."""
        return False

    def has_delete_permission(self, request, obj=None):  # type: ignore[no-untyped-def]
        """KeyValue entries are managed programmatically."""
        return False
