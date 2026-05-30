# Generated manually for generic LangGraph workflow templates.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("runs", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="WorkflowTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=120, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("version", models.CharField(default="1.0", max_length=24)),
                ("nodes", models.JSONField(default=list)),
                ("edges", models.JSONField(default=list)),
                ("input_schema", models.JSONField(default=dict)),
                ("output_schema", models.JSONField(default=dict)),
                ("default_agents", models.JSONField(default=list)),
                ("is_active", models.BooleanField(default=True)),
            ],
            options={
                "ordering": ["name", "version"],
            },
        ),
    ]