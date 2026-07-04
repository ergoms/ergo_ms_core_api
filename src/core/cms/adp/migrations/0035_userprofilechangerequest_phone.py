# -*- coding: utf-8 -*-

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0034_flatten_user_account_menu'),
    ]

    operations = [
        migrations.AddField(
            model_name='userprofilechangerequest',
            name='phone',
            field=models.CharField(blank=True, default='', max_length=20, verbose_name='Телефон'),
        ),
    ]
