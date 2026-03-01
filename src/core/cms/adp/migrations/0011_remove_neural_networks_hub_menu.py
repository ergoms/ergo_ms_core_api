# -*- coding: utf-8 -*-
"""
Удаляет меню модуля neural_networks_hub из core-миграций.
Теперь меню создаётся миграцией внутри самого модуля
(modules/neural_networks_hub/api/migrations/0010_add_menu.py).
"""

from django.db import migrations

ROLE_GROUP_TEACHER = 'Преподаватель (НН)'
ROLE_GROUP_STUDENT = 'Студент (НН)'


def remove_nn_hub_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    RoleGroup = apps.get_model('cms_adp', 'RoleGroup')
    MenuItem.objects.filter(module_source='modules/neural_networks_hub').delete()
    RoleGroup.objects.filter(
        name__in=[ROLE_GROUP_TEACHER, ROLE_GROUP_STUDENT]
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0010_add_neural_networks_hub_menu'),
    ]

    operations = [
        migrations.RunPython(remove_nn_hub_menu, migrations.RunPython.noop),
    ]
