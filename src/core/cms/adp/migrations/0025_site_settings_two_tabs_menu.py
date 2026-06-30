# -*- coding: utf-8 -*-

from django.db import migrations


def restructure_site_settings_menu(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0024_theme_editor_top_level_menu'),
    ]

    operations = [
        migrations.RunPython(
            restructure_site_settings_menu,
            migrations.RunPython.noop,
        ),
    ]
