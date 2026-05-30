from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("messaging", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="channelconversation",
            name="external_channel",
            field=models.CharField(default="discord", max_length=24),
        ),
    ]
