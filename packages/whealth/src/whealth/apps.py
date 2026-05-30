"""App configuration for whealth."""

from django.apps import AppConfig


class WhealthConfig(AppConfig):
    """Django app configuration for the whealth health-checking app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "whealth"
