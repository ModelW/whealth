"""Add UUID PK, state field, and sentry_checkin_id to CheckIn model."""
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("whealth", "0004_incident_date_ignored"),
    ]

    operations = [
        migrations.AddField(
            model_name="checkin",
            name="state",
            field=models.CharField(
                choices=[
                    ("started", "Started"),
                    ("finished", "Finished"),
                    ("failed", "Failed"),
                ],
                default="started",
                help_text="Current state of this check-in.",
                max_length=16,
                verbose_name="state",
            ),
        ),
        migrations.AddField(
            model_name="checkin",
            name="sentry_checkin_id",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Sentry check-in ID returned by capture_checkin.",
                max_length=64,
                verbose_name="sentry check-in ID",
            ),
        ),
        migrations.AlterField(
            model_name="checkin",
            name="id",
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                primary_key=True,
                serialize=False,
            ),
        ),
    ]
