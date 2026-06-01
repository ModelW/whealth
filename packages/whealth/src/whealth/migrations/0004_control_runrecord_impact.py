"""Add impact to Control and RunRecord, backfill historical data."""

from __future__ import annotations

import os
from pathlib import Path

from django.db import migrations, models


def _parse_impact_from_manifest(pkg_dir: str) -> str:
    """Read impact from a control's manifest.yaml, defaulting to 'major'."""
    manifest_path = Path(pkg_dir) / "manifest.yaml"
    try:
        text = manifest_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return "major"
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("impact:"):
            val = stripped.split(":", 1)[1].strip()
            if val in ("critical", "major", "minor"):
                return val
    return "major"


def backfill_control_impact(apps, schema_editor) -> None:
    """Populate Control.impact from manifest files for whealth's builtins."""
    Control = apps.get_model("whealth", "Control")

    _IMPACT_MAP: dict[str, str] = {}

    # Manifests are located relative to the whealth package.
    controls_root = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "controls",
    )

    for slug in ("database", "cache", "storage", "crons"):
        pkg_dir = os.path.join(controls_root, slug)
        _IMPACT_MAP[slug] = _parse_impact_from_manifest(pkg_dir)

    for row in Control.objects.iterator():
        impact = _IMPACT_MAP.get(row.slug, "major")
        if row.impact != impact:
            row.impact = impact
            row.save(update_fields=["impact"])


def backfill_runrecord_impact(apps, schema_editor) -> None:
    """Compute impact for each RunRecord from its results and Control.impact."""
    RunRecord = apps.get_model("whealth", "RunRecord")
    Control = apps.get_model("whealth", "Control")

    impact_by_key: dict[tuple[str, str], str] = {}
    for ctrl in Control.objects.iterator():
        impact_by_key[(ctrl.app_label, ctrl.slug)] = ctrl.impact

    _IMPACT_ORDER = {"none": 0, "critical": 3, "major": 2, "minor": 1}

    for record in RunRecord.objects.iterator():
        if not record.results:
            if record.impact != "none":
                record.impact = "none"
                record.save(update_fields=["impact"])
            continue

        impacts: list[str] = []
        for label, result in record.results.items():
            if result is None:
                continue
            if not isinstance(result, list):
                continue
            if not result:
                continue
            if "." not in label:
                continue
            app_label, slug = label.split(".", 1)
            impact = impact_by_key.get((app_label, slug), "major")
            impacts.append(impact)

        if not impacts:
            computed = "none"
        else:
            computed = max(impacts, key=lambda i: _IMPACT_ORDER.get(i, 0))

        if record.impact != computed:
            record.impact = computed
            record.save(update_fields=["impact"])


class Migration(migrations.Migration):

    dependencies = [
        ("whealth", "0003_alter_runrecord_duration"),
    ]

    operations = [
        migrations.AddField(
            model_name="control",
            name="impact",
            field=models.CharField(
                default="major",
                help_text="Impact level of this control. "
                "One of ``critical``, ``major``, or ``minor``.",
                max_length=16,
                verbose_name="impact",
            ),
        ),
        migrations.RunPython(
            backfill_control_impact,
            migrations.RunPython.noop,
        ),
        migrations.AddField(
            model_name="runrecord",
            name="impact",
            field=models.CharField(
                default="none",
                help_text="Highest impact level among controls that failed in "
                "this run. One of ``critical``, ``major``, ``minor``, or "
                "``none``.",
                max_length=16,
                verbose_name="impact",
            ),
        ),
        migrations.RunPython(
            backfill_runrecord_impact,
            migrations.RunPython.noop,
        ),
    ]
