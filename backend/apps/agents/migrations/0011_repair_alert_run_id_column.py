from __future__ import annotations

from django.db import migrations


def repair_alert_run_id_column(apps, schema_editor):
    table_name = "agents_alert"
    existing_tables = set(schema_editor.connection.introspection.table_names())
    if table_name not in existing_tables:
        return

    with schema_editor.connection.cursor() as cursor:
        table_description = schema_editor.connection.introspection.get_table_description(cursor, table_name)
        columns = {column.name for column in table_description}
        if "run_id" in columns:
            return

    schema_editor.execute(
        f'ALTER TABLE "{table_name}" '
        'ADD COLUMN "run_id" varchar(36) NOT NULL DEFAULT ""'
    )


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0010_repair_agentmemory_run_id_column"),
    ]

    operations = [
        migrations.RunPython(repair_alert_run_id_column, migrations.RunPython.noop),
    ]