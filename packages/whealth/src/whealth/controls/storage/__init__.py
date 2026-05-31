"""Storage health control."""

from __future__ import annotations

from django.conf import settings
from django.core.files.storage import storages
from whealth import BaseControl, Failure


class Control(BaseControl):
    """Check that every configured storage backend is reachable."""

    def get_failures(self) -> list[Failure]:
        """Run the storage health check."""
        failures: list[Failure] = []
        for alias in settings.STORAGES:
            storage = storages[alias]
            try:
                storage.exists("_whealth_ping")
            except Exception:
                failures.append(Failure(key=alias, outcome="error"))
        return failures
