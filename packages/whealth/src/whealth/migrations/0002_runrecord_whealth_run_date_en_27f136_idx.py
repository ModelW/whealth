"""Add index for fast latest-run query."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("whealth", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="runrecord",
            index=models.Index(
                fields=["date_end", "date_start"],
                name="whealth_run_date_en_27f136_idx",
            ),
        ),
    ]
