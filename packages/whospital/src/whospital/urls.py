"""URL configuration for whospital."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("whealth/", include("whealth.urls")),
]
