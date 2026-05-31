"""Database health control."""

from __future__ import annotations

from django.conf import settings
from django.db import connections
from whealth import BaseControl, Failure


class Control(BaseControl):
    """Check that every configured database connection is alive."""

    def get_failures(self) -> list[Failure]:
        """Run the database health check."""
        failures: list[Failure] = []
        for alias in settings.DATABASES:
            conn = connections[alias]
            try:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
            except Exception:
                failures.append(Failure(key=alias, outcome="error"))
        return failures
