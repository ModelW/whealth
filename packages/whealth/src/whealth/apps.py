"""App configuration for whealth."""

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class WhealthConfig(AppConfig):
    """Django app configuration for the whealth health-checking app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "whealth"
    verbose_name = _("Health Checks")

    def ready(self) -> None:
        """Install whealth's Procrastinate middleware automatically.

        Works with any ``INSTALLED_APPS`` ordering, and is a no-op when
        procrastinate is not installed:

        * If ``procrastinate.contrib.django`` is listed *before*
          whealth, its app already exists — install directly.
        * Otherwise, its app is not created yet — register the install
          through procrastinate's own ``PROCRASTINATE_ON_APP_READY``
          hook, which its ``ready()`` calls with the real app.  Any
          hook the user configured themselves is preserved and called
          first (see :func:`whealth.procrastinate.on_app_ready`).
        """
        try:
            import procrastinate
            from procrastinate.contrib.django import procrastinate_app
        except ImportError:
            return

        import whealth.procrastinate
        from whealth.procrastinate import install_middleware

        if isinstance(procrastinate_app.current_app, procrastinate.App):
            install_middleware(procrastinate_app.current_app)
            return

        from django.conf import settings

        ours = "whealth.procrastinate.on_app_ready"
        existing = getattr(settings, "PROCRASTINATE_ON_APP_READY", None)
        if existing and existing != ours:
            whealth.procrastinate.chained_on_app_ready = existing
        settings.PROCRASTINATE_ON_APP_READY = ours
