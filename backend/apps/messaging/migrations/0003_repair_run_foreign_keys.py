# Generated manually to repair stale workflow run foreign keys.

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("runs", "0001_initial"),
        ("messaging", "0002_alter_channelconversation_external_channel"),
    ]

    operations = [
        migrations.AlterField(
            model_name="channelconversation",
            name="active_run",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="runs.unifiedrun",
            ),
        ),
        migrations.AlterField(
            model_name="interagentmessage",
            name="run",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="messages",
                to="runs.unifiedrun",
            ),
        ),
        migrations.AlterField(
            model_name="approvalticket",
            name="run",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="approvals",
                to="runs.unifiedrun",
            ),
        ),
    ]
