"""Models for whospital_apps."""

from django.db import models
from django.utils.translation import gettext_lazy as _


class KeyValue(models.Model):
    """A simple key-value store for testing health controls."""

    key = models.CharField(  # type: ignore[var-annotated]
        max_length=128,
        unique=True,
        help_text=_("Unique key for this value."),
        verbose_name=_("key"),
    )
    value = models.TextField(  # type: ignore[var-annotated]
        blank=True,
        default="",
        help_text=_("Arbitrary value associated with this key."),
        verbose_name=_("value"),
    )

    class Meta:
        verbose_name = _("key value")
        verbose_name_plural = _("key values")

    def __str__(self) -> str:
        return f"{self.key}={self.value}"
