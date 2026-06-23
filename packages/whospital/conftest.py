# ruff: noqa: INP001
"""Pytest configuration for whospital.

pytest-testcontainers-django handles starting Postgres and injecting env
vars before Django settings are loaded. Configuration is in pyproject.toml.
"""

from __future__ import annotations

import os
from typing import Any

import pytest_testcontainers_django.injection  # type: ignore[import-untyped]
import pytest_testcontainers_django.plugin  # type: ignore[import-untyped]

# Intercept the testcontainers env-var injection to also set DATABASE_URL
# before pytest-django loads settings.py. This keeps settings.py 100% pristine.
_original_inject = pytest_testcontainers_django.injection.inject


def _patched_inject(config: Any, *args: Any, **kwargs: Any) -> Any:
    snapshot = _original_inject(config, *args, **kwargs)
    pg = config.postgres

    host = os.environ.get(pg.env_names["host"])
    port = os.environ.get(pg.env_names["port"])
    name = os.environ.get(pg.env_names["name"])
    user = os.environ.get(pg.env_names["user"])
    password = os.environ.get(pg.env_names["password"])

    if host and port:
        os.environ["DATABASE_URL"] = (
            f"postgresql://{user}:{password}@{host}:{port}/{name}"
        )
        snapshot.keys = (*snapshot.keys, "DATABASE_URL")
        snapshot.previous["DATABASE_URL"] = None

    return snapshot


# Patch in both namespaces to handle "from injection import inject" imports
pytest_testcontainers_django.injection.inject = _patched_inject
pytest_testcontainers_django.plugin.inject = _patched_inject
