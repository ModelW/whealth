"""Cache health control."""

from __future__ import annotations

from django.conf import settings
from django.core.cache import caches
from whealth import BaseControl, Failure


class Control(BaseControl):
    """Check that every configured cache backend is reachable."""

    def get_failures(self) -> list[Failure]:
        """Run the cache health check."""
        failures: list[Failure] = []
        for alias in settings.CACHES:
            cache = caches[alias]
            try:
                cache.get_or_set("_whealth_ping", True, 5)
            except Exception:
                failures.append(Failure(key=alias, outcome="error"))
        return failures
