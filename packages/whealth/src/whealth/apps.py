"""App configuration for whealth."""

from django.apps import AppConfig
from django.db import ProgrammingError


class WhealthConfig(AppConfig):
    """Django app configuration for the whealth health-checking app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "whealth"

    def ready(self) -> None:
        """Discover and register all controls on startup."""
        from whealth.registry import get_control_registry

        try:
            get_control_registry().sync_to_db()
        except ProgrammingError:
            pass
