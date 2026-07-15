from django.db import migrations

LEGACY_THEME_INDEX_RENAMES = (
    ('settings_th_module__a1b2c3_idx', 'settings_th_module__48e8e9_idx'),
    ('settings_th_module__d4e5f6_idx', 'settings_th_module__0d2baf_idx'),
)


def rename_legacy_theme_indexes(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != 'postgresql':
        return

    with connection.cursor() as cursor:
        for old_name, new_name in LEGACY_THEME_INDEX_RENAMES:
            cursor.execute(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname = %s
                """,
                [old_name],
            )
            if not cursor.fetchone():
                continue

            cursor.execute(
                """
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = current_schema()
                  AND indexname = %s
                """,
                [new_name],
            )
            if cursor.fetchone():
                continue

            cursor.execute(
                f'ALTER INDEX "{old_name}" RENAME TO "{new_name}"',
            )


class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0024_seed_ai_assistant_module_themes'),
    ]

    operations = [
        migrations.RunPython(rename_legacy_theme_indexes, migrations.RunPython.noop),
    ]
