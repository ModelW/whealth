"""ASGI configuration for whospital."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "whospital.settings")

application = get_asgi_application()
