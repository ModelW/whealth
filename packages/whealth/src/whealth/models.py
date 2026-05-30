"""Models for the whealth health-checking app."""

from typing import ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _


class Cron(models.Model):
    """A cron-based health check that expects periodic check-ins."""

    class ScheduleType(models.TextChoices):
        """Supported scheduling mechanisms."""

        CRONTAB = "crontab", _("Crontab")

    slug = models.SlugField(
        max_length=128,
        unique=True,
        help_text=_("Unique text identifier for this cron check."),
        verbose_name=_("slug"),
    )
    schedule_type = models.CharField(
        max_length=16,
        choices=ScheduleType.choices,
        default=ScheduleType.CRONTAB,
        help_text=_("Type of scheduling mechanism used for this cron."),
        verbose_name=_("schedule type"),
    )
    schedule = models.CharField(
        max_length=256,
        help_text=_(
            "Schedule representation. For crontab this must be a valid "
            "crontab expression (e.g. '*/5 * * * *')."
        ),
        verbose_name=_("schedule"),
    )
    timezone = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text=_(
            "Timezone for this schedule. Leave empty to use the Django "
            "default timezone."
        ),
        verbose_name=_("timezone"),
    )
    checkin_margin = models.DurationField(
        help_text=_("Maximum allowed delay before a check-in is considered missed."),
        verbose_name=_("check-in margin"),
    )
    max_runtime = models.DurationField(
        help_text=_("Maximum expected runtime for the associated task."),
        verbose_name=_("max runtime"),
    )
    failure_issue_threshold = models.PositiveIntegerField(
        default=2,
        help_text=_(
            "Number of consecutive missed check-ins required to consider "
            "this cron as failed."
        ),
        verbose_name=_("failure issue threshold"),
    )
    recovery_threshold = models.PositiveIntegerField(
        default=1,
        help_text=_(
            "Number of successful check-ins after a failure required to "
            "consider this cron back on track."
        ),
        verbose_name=_("recovery threshold"),
    )

    class Meta:
        verbose_name = _("cron")
        verbose_name_plural = _("crons")

    def __str__(self) -> str:
        return self.slug


class CheckIn(models.Model):
    """A single check-in event for a cron health check."""

    cron = models.ForeignKey(
        Cron,
        on_delete=models.CASCADE,
        related_name="checkins",
        help_text=_("Cron check that this check-in belongs to."),
        verbose_name=_("cron"),
    )
    start = models.DateTimeField(
        help_text=_("Timestamp of when this check-in started."),
        verbose_name=_("start"),
    )
    end = models.DateTimeField(
        blank=True,
        null=True,
        help_text=_("Timestamp of when this check-in ended. Null while still running."),
        verbose_name=_("end"),
    )

    class Meta:
        verbose_name = _("check-in")
        verbose_name_plural = _("check-ins")

    def __str__(self) -> str:
        return f"{self.cron.slug} @ {self.start}"


class Control(models.Model):
    """A control that verifies a specific aspect of the application's health."""

    slug = models.SlugField(
        max_length=128,
        unique=True,
        help_text=_("Unique textual reference for this control."),
        verbose_name=_("slug"),
    )
    title = models.CharField(
        max_length=256,
        help_text=_("Human-readable title for this control."),
        verbose_name=_("title"),
    )
    description = models.TextField(
        blank=True,
        default="",
        help_text=_(
            "Full markdown description and operational manual for this "
            "control — explains what is checked and what to do on failure."
        ),
        verbose_name=_("description"),
    )
    depends_on = models.ManyToManyField(
        "self",
        symmetrical=False,
        blank=True,
        help_text=_(
            "Other controls that this control depends on. If a dependency "
            "fails, this control is considered affected."
        ),
        verbose_name=_("depends on"),
    )

    class Meta:
        verbose_name = _("control")
        verbose_name_plural = _("controls")

    def __str__(self) -> str:
        return self.title or self.slug


class Incident(models.Model):
    """An incident raised when a control check turns negative."""

    date_start = models.DateTimeField(
        help_text=_("Timestamp when this incident started."),
        verbose_name=_("date start"),
    )
    date_end = models.DateTimeField(
        blank=True,
        null=True,
        help_text=_("Timestamp when this incident ended. Null while still active."),
        verbose_name=_("date end"),
    )
    control = models.ForeignKey(
        Control,
        on_delete=models.CASCADE,
        related_name="incidents",
        help_text=_("Control associated with this incident."),
        verbose_name=_("control"),
    )
    key = models.CharField(
        max_length=256,
        help_text=_(
            "Instance key for this incident. A (control, key) tuple uniquely "
            "identifies an open incident — the same control can fail on "
            "different instances concurrently."
        ),
        verbose_name=_("key"),
    )
    context = models.TextField(
        blank=True,
        default="",
        help_text=_("Optional markdown context describing what happened."),
        verbose_name=_("context"),
    )

    class Meta:
        verbose_name = _("incident")
        verbose_name_plural = _("incidents")

        # List of database constraints.
        constraints: ClassVar[list[models.BaseConstraint]] = [
            models.UniqueConstraint(
                fields=["control", "key", "date_end"],
                name="unique_open_incident",
                condition=models.Q(date_end__isnull=True),
                violation_error_message=_(
                    "An open incident already exists for this control and key."
                ),
            ),
        ]

    def __str__(self) -> str:
        return f"{self.control.slug}/{self.key}"
