# -*- coding: utf-8 -*-
"""Удаление таблиц и записей миграций app graduate_employment."""

from django.db import migrations


def drop_graduate_employment_schema(apps, schema_editor):
    connection = schema_editor.connection
    table_names = connection.introspection.table_names()
    prefix = 'graduate_employment_'
    for table in table_names:
        if table.startswith(prefix):
            schema_editor.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')

    with connection.cursor() as cursor:
        cursor.execute("DELETE FROM django_migrations WHERE app = %s", ['graduate_employment'])


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0041_remove_graduate_employment_menu'),
    ]

    operations = [
        migrations.RunPython(drop_graduate_employment_schema, migrations.RunPython.noop),
    ]
