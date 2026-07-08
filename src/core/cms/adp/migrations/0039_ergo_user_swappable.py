# -*- coding: utf-8 -*-
"""
ErgoUser в state Django без изменений физической таблицы auth_user.

Колонки middle_name и public_id уже добавлены cms_adp.0038.
"""

import django.contrib.auth.models
import django.contrib.auth.validators
import django.utils.timezone
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('cms_adp', '0038_user_extension_fields'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.CreateModel(
                    name='ErgoUser',
                    fields=[
                        ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                        ('password', models.CharField(max_length=128, verbose_name='password')),
                        ('last_login', models.DateTimeField(blank=True, null=True, verbose_name='last login')),
                        ('is_superuser', models.BooleanField(default=False, help_text='Designates that this user has all permissions without explicitly assigning them.', verbose_name='superuser status')),
                        ('username', models.CharField(error_messages={'unique': 'A user with that username already exists.'}, help_text='Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only.', max_length=150, unique=True, validators=[django.contrib.auth.validators.UnicodeUsernameValidator()], verbose_name='username')),
                        ('first_name', models.CharField(blank=True, max_length=150, verbose_name='first name')),
                        ('last_name', models.CharField(blank=True, max_length=150, verbose_name='last name')),
                        ('email', models.EmailField(blank=True, max_length=254, verbose_name='email address')),
                        ('is_staff', models.BooleanField(default=False, help_text='Designates whether the user can log into this admin site.', verbose_name='staff status')),
                        ('is_active', models.BooleanField(default=True, help_text='Designates whether this user should be treated as active. Unselect this instead of deleting accounts.', verbose_name='active')),
                        ('date_joined', models.DateTimeField(default=django.utils.timezone.now, verbose_name='date joined')),
                        ('middle_name', models.CharField(blank=True, default='', max_length=150, verbose_name='Отчество')),
                        ('public_id', models.UUIDField(default=uuid.uuid4, editable=False, null=True, unique=True, verbose_name='public id')),
                        ('groups', models.ManyToManyField(blank=True, help_text='The groups this user belongs to. A user will get all permissions granted to each of their groups.', related_name='user_set', related_query_name='user', to='auth.group', verbose_name='groups')),
                        ('user_permissions', models.ManyToManyField(blank=True, help_text='Specific permissions for this user.', related_name='user_set', related_query_name='user', to='auth.permission', verbose_name='user permissions')),
                    ],
                    options={
                        'verbose_name': 'пользователь',
                        'verbose_name_plural': 'пользователи',
                        'db_table': 'auth_user',
                    },
                    managers=[
                        ('objects', django.contrib.auth.models.UserManager()),
                    ],
                ),
            ],
        ),
    ]
