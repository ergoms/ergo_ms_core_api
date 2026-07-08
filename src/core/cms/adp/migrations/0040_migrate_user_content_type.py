# -*- coding: utf-8 -*-
"""
Перенос ContentType и Permission с auth.user на cms_adp.ergouser.

Идемпотентная data-миграция: безопасна для повторного применения.
"""

from django.db import migrations


def migrate_user_content_type(apps, schema_editor):
    ContentType = apps.get_model('contenttypes', 'ContentType')
    Permission = apps.get_model('auth', 'Permission')

    old_ct = ContentType.objects.filter(app_label='auth', model='user').first()
    new_ct, _ = ContentType.objects.get_or_create(
        app_label='cms_adp',
        model='ergouser',
    )

    if old_ct is None:
        return

    if old_ct.pk != new_ct.pk:
        Permission.objects.filter(content_type_id=old_ct.pk).update(content_type_id=new_ct.pk)
        old_ct.delete()
    else:
        old_ct.app_label = 'cms_adp'
        old_ct.model = 'ergouser'
        old_ct.save(update_fields=['app_label', 'model'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('auth', '0012_alter_user_first_name_max_length'),
        ('cms_adp', '0039_ergo_user_swappable'),
    ]

    operations = [
        migrations.RunPython(migrate_user_content_type, noop_reverse),
    ]
