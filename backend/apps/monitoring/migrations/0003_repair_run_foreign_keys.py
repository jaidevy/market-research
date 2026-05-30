# Generated manually to repair stale workflow run foreign keys.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("runs", "0001_initial"),
        ("monitoring", "0002_alter_tokencostledger_model_name_default"),
    ]

    operations = [
        migrations.AlterField(
            model_name="runtimeevent",
            name="run",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="events",
                to="runs.unifiedrun",
            ),
        ),
        migrations.AlterField(
            model_name="tokencostledger",
            name="run",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="token_costs",
                to="runs.unifiedrun",
            ),
        ),
    ]
