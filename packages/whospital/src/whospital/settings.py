"""Django settings for whospital."""

import os
import tempfile
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "django-insecure-whospital-dev-key"  # noqa: S105
DEBUG = True
ROOT_URLCONF = "whospital.urls"
WSGI_APPLICATION = "whospital.wsgi.application"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "procrastinate.contrib.django",
    "whealth",
    "whospital_apps",
]

MIDDLEWARE = [
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

DATABASES = {
    "default": dj_database_url.config(
        default="sqlite:///" + str(Path(tempfile.gettempdir()) / "whospital.sqlite"),
    ),
}

# If pytest-testcontainers-django injected individual env vars, assemble
# a DATABASE_URL from them as a fallback (takes precedence over the default
# only when the plugin is active).
_db_url_from_parts = os.environ.get("DATABASE_URL") or (
    os.environ.get("DJANGO_DB_HOST")
    and (
        f"postgresql://{os.environ['DJANGO_DB_USER']}:{os.environ['DJANGO_DB_PASSWORD']}"
        f"@{os.environ['DJANGO_DB_HOST']}:{os.environ['DJANGO_DB_PORT']}"
        f"/{os.environ['DJANGO_DB_NAME']}"
    )
)
if _db_url_from_parts:
    DATABASES["default"] = dj_database_url.parse(_db_url_from_parts)
