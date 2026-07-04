# -*- coding: utf-8 -*-

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0032_remove_users_all_submenu'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='website',
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='country',
        ),
        migrations.RemoveField(
            model_name='userprofile',
            name='city',
        ),
    ]
