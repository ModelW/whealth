"""Models for the whealth health-checking app."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, ClassVar

from django.db import models
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from whealth.runner import ControlRunner


class RunRecord(models.Model):
    """A snapshot of a full control run — all results at a point in time."""

    date_start = models.DateTimeField(
        help_text=_("Timestamp when this run started."),
        verbose_name=_("date start"),
    )
    date_end = models.DateTimeField(
        blank=True,
        null=True,
        help_text=_("Timestamp when this run completed. Null while still running."),
        verbose_name=_("date end"),
    )
    duration = models.DurationField(
        blank=True,
        null=True,
        help_text=_("Wall-clock duration of this run."),
        verbose_name=_("duration"),
    )
    hostname = models.CharField(
        max_length=255,
        help_text=_("Hostname of the machine that performed this run."),
        verbose_name=_("hostname"),
    )
    cli = models.CharField(
        max_length=1024,
        blank=True,
        default="",
        help_text=_("CLI command that triggered this run (sys.argv)."),
        verbose_name=_("CLI"),
    )
    results = models.JSONField(
        blank=True,
        default=dict,
        help_text=_(
            "Full results snapshot — mapping of ``app_label.slug`` to "
            "a list of serialised Failure dicts, or ``null`` for blocked."
        ),
        verbose_name=_("results"),
    )

    class Meta:
        verbose_name = _("run record")
        verbose_name_plural = _("run records")
        get_latest_by = "date_start"
        ordering = ("-date_start",)
        indexes = [  # noqa: RUF012
            models.Index(
                fields=["date_end", "date_start"], name="whealth_run_date_en_27f136_idx"
            ),
        ]

    def __str__(self) -> str:
        return f"Run @ {self.date_start} on {self.hostname}"

    def get_runner(self) -> ControlRunner:
        """Return a re-hydrated ControlRunner instance representing this run."""
        from whealth.registry import get_control_registry
        from whealth.runner import ControlRunner

        registry = get_control_registry()
        return ControlRunner.from_results(self.results, registry)


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

    class State(models.TextChoices):
        """Possible states of a check-in."""

        STARTED = "started", _("Started")
        FINISHED = "finished", _("Finished")
        FAILED = "failed", _("Failed")

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    state = models.CharField(
        max_length=16,
        choices=State.choices,
        default=State.STARTED,
        help_text=_("Current state of this check-in."),
        verbose_name=_("state"),
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
    app_label = models.CharField(
        max_length=128,
        help_text=_("Django app label that discovered this control."),
        verbose_name=_("app label"),
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
    active = models.BooleanField(
        default=True,
        help_text=_("Whether this control is still discovered by the registry."),
        verbose_name=_("active"),
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
    date_ignored = models.DateTimeField(
        blank=True,
        null=True,
        help_text=_(
            "Timestamp when this incident was last ignored. Null if never "
            "ignored or still active."
        ),
        verbose_name=_("date ignored"),
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
    context = models.JSONField(
        blank=True,
        default=dict,
        help_text=_(
            "Opaque JSON-serializable value providing context about what "
            "caused this incident."
        ),
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
