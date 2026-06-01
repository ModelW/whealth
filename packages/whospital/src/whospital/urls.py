"""URL configuration for whospital."""

from django.contrib import admin
from django.urls import include, path

admin.site.site_title = "Whealth"
admin.site.site_header = "Whealth"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("whealth/", include("whealth.urls")),
]
