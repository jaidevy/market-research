from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("agents", "0008_add_trade_memory"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="agent",
            name="model",
        ),
    ]