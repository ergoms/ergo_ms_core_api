# -*- coding: utf-8 -*-
"""
Идемпотентный ремонт ACL MenuSeparator.

0056 добавляет is_admin_only / allowed_* , 0059 пустая (операции перенесены в 0056).
На установках, где 0056/0059 уже были в django_migrations до появления AddField
в файле 0056, колонок и M2M-таблиц нет, а migrate их не повторяет.

Здесь только schema DB: state Django уже содержит поля с 0056.
"""

from django.apps import apps as global_apps
from django.db import migrations


def _table_columns(schema_editor, table_name):
    connection = schema_editor.connection
    with connection.cursor() as cursor:
        description = connection.introspection.get_table_description(cursor, table_name)
    return {col.name for col in description}


def ensure_menuseparator_access_acl(apps, schema_editor):
    MenuSeparator = global_apps.get_model('cms_adp', 'MenuSeparator')
    connection = schema_editor.connection
    existing_tables = set(connection.introspection.table_names())
    table = MenuSeparator._meta.db_table
    if table not in existing_tables:
        return

    columns = _table_columns(schema_editor, table)
    if 'is_admin_only' not in columns:
        schema_editor.add_field(
            MenuSeparator,
            MenuSeparator._meta.get_field('is_admin_only'),
        )

    existing_tables = set(connection.introspection.table_names())
    for field_name in ('allowed_roles', 'allowed_role_groups'):
        field = MenuSeparator._meta.get_field(field_name)
        through = field.remote_field.through
        through_table = through._meta.db_table
        if through_table not in existing_tables:
            schema_editor.create_model(through)
            existing_tables.add(through_table)


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0062_remove_policy_type_component'),
    ]

    operations = [
        migrations.RunPython(
            ensure_menuseparator_access_acl,
            migrations.RunPython.noop,
        ),
    ]
