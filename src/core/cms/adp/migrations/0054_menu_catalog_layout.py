# -*- coding: utf-8 -*-
"""Каталог/layout меню: catalog_key, MenuLayoutPlacement, MenuSeparatorLayout."""

from django.db import migrations, models

# Не включать RunPython в цепочку restore_menu (одноразовый backfill схемы).
MENU_RESTORE_SKIP = True


def _backfill_catalog_and_layout(apps, schema_editor):
    from src.core.cms.adp.menu.catalog_keys import (
        build_item_catalog_key,
        build_separator_catalog_key,
    )

    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuSeparator = apps.get_model('cms_adp', 'MenuSeparator')
    MenuLayoutPlacement = apps.get_model('cms_adp', 'MenuLayoutPlacement')
    MenuSeparatorLayout = apps.get_model('cms_adp', 'MenuSeparatorLayout')

    # Сначала корни, затем дети (для folder-ключей с parent)
    pending = list(MenuItem.objects.all().order_by('id'))
    assigned = {}

    # Несколько проходов — пока назначаются ключи с учётом родителя
    for _ in range(8):
        progress = False
        for item in pending:
            if item.id in assigned:
                continue
            parent_key = None
            if item.parent_id:
                if item.parent_id not in assigned:
                    continue
                parent_key = assigned[item.parent_id]
            key = build_item_catalog_key(
                item.module_source,
                item_type=item.item_type or 'route',
                route_name=item.route_name,
                page=item.page,
                external_url=item.external_url,
                name=item.name,
                parent_catalog_key=parent_key,
                public_id=str(item.public_id),
            )
            # коллизии — суффикс public_id
            if MenuItem.objects.filter(catalog_key=key).exclude(pk=item.pk).exists():
                key = f'{key}::{item.public_id}'
            item.catalog_key = key
            item.save(update_fields=['catalog_key'])
            assigned[item.id] = key
            progress = True

            parent_catalog_key = parent_key
            MenuLayoutPlacement.objects.update_or_create(
                catalog_key=key,
                defaults={
                    'parent_catalog_key': parent_catalog_key,
                    'order': item.order if item.order is not None else 0,
                    'is_active': item.is_active,
                },
            )
        if len(assigned) == len(pending):
            break
        if not progress:
            for item in pending:
                if item.id in assigned:
                    continue
                key = f'admin::{item.public_id}'
                item.catalog_key = key
                item.save(update_fields=['catalog_key'])
                assigned[item.id] = key
                MenuLayoutPlacement.objects.update_or_create(
                    catalog_key=key,
                    defaults={
                        'parent_catalog_key': assigned.get(item.parent_id),
                        'order': item.order if item.order is not None else 0,
                        'is_active': item.is_active,
                    },
                )
            break

    root_by_order = list(
        MenuItem.objects.filter(parent__isnull=True).order_by('order', 'name')
    )

    for sep in MenuSeparator.objects.all():
        # Исторические разделители без module_source — из core seed
        source = (sep.module_source or '').strip() or 'core/cms'
        key = build_separator_catalog_key(source, sep.name, public_id=str(sep.public_id))
        if MenuSeparator.objects.filter(catalog_key=key).exclude(pk=sep.pk).exists():
            key = f'admin::separator::{sep.public_id}'
            source = None
        sep.catalog_key = key
        if source and not sep.module_source:
            sep.module_source = source

        before_key = None
        for item in root_by_order:
            order = item.order if item.order is not None else 0
            if order >= (sep.before_order or 0):
                before_key = item.catalog_key
                break
        sep.before_catalog_key = before_key
        sep.save(update_fields=['catalog_key', 'before_catalog_key', 'module_source'])

        MenuSeparatorLayout.objects.update_or_create(
            catalog_key=key,
            defaults={
                'name': sep.name,
                'before_catalog_key': before_key,
                'before_order': sep.before_order or 0,
                'is_active': sep.is_active,
            },
        )


def _noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0053_repopulate_menu_after_schema_recreate'),
    ]

    operations = [
        migrations.AddField(
            model_name='menuitem',
            name='catalog_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Стабильный ключ seed/админа; не зависит от PK',
                max_length=512,
                null=True,
                unique=True,
                verbose_name='Ключ каталога',
            ),
        ),
        migrations.AddField(
            model_name='menuseparator',
            name='catalog_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                max_length=512,
                null=True,
                unique=True,
                verbose_name='Ключ каталога',
            ),
        ),
        migrations.AddField(
            model_name='menuseparator',
            name='module_source',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                verbose_name='Модуль-источник',
            ),
        ),
        migrations.AddField(
            model_name='menuseparator',
            name='before_catalog_key',
            field=models.CharField(
                blank=True,
                db_index=True,
                help_text='Якорь: разделитель перед пунктом с этим catalog_key',
                max_length=512,
                null=True,
                verbose_name='Перед пунктом (ключ каталога)',
            ),
        ),
        migrations.CreateModel(
            name='MenuLayoutPlacement',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('catalog_key', models.CharField(db_index=True, max_length=512, unique=True, verbose_name='Ключ каталога')),
                ('parent_catalog_key', models.CharField(blank=True, db_index=True, max_length=512, null=True, verbose_name='Ключ родителя')),
                ('order', models.PositiveIntegerField(default=0, verbose_name='Порядок')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Размещение пункта меню',
                'verbose_name_plural': 'Размещения пунктов меню',
                'ordering': ['order', 'catalog_key'],
            },
        ),
        migrations.CreateModel(
            name='MenuSeparatorLayout',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('catalog_key', models.CharField(db_index=True, max_length=512, unique=True, verbose_name='Ключ каталога')),
                ('name', models.CharField(blank=True, default='', max_length=100, verbose_name='Название')),
                ('before_catalog_key', models.CharField(blank=True, max_length=512, null=True, verbose_name='Перед пунктом')),
                ('before_order', models.PositiveIntegerField(default=0, verbose_name='Перед порядком')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Размещение разделителя',
                'verbose_name_plural': 'Размещения разделителей',
                'ordering': ['before_order', 'catalog_key'],
            },
        ),
        migrations.RunPython(_backfill_catalog_and_layout, _noop_reverse),
    ]
