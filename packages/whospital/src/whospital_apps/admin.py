"""Admin configuration for whospital_apps."""

from __future__ import annotations

from django.contrib import admin

from whospital_apps.models import KeyValue


@admin.register(KeyValue)
class KeyValueAdmin(admin.ModelAdmin):  # type: ignore[type-arg]
    """Admin interface for KeyValue entries."""
