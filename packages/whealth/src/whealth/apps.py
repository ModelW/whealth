"""App configuration for whealth."""

from django.apps import AppConfig


class WhealthConfig(AppConfig):
    """Django app configuration for the whealth health-checking app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "whealth"

    def ready(self) -> None:
        """Discover and register all controls on startup."""
        from whealth.registry import get_control_registry

        get_control_registry().discover()
