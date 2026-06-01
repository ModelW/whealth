"""App configuration for whealth."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WhealthConfig(AppConfig):
    """Django app configuration for the whealth health-checking app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "whealth"
    verbose_name = _("Health Checks")
