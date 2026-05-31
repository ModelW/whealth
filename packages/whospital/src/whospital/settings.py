"""Django settings for whospital."""

from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = "django-insecure-whospital-dev-key"  # noqa: S105
DEBUG = True
ROOT_URLCONF = "whospital.urls"
WSGI_APPLICATION = "whospital.wsgi.application"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "whealth",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "procrastinate.contrib.django",
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

USE_TZ = True
TIME_ZONE = "Europe/Madrid"

DATABASES = {
    "default": dj_database_url.config(
        default="postgresql://whealth:whealth@localhost/whealth",
    ),
}
