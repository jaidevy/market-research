from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0004_skill"),
    ]

    operations = [
        migrations.AddField(
            model_name="agent",
            name="description",
            field=models.TextField(blank=True, default=""),
        ),
    ]
