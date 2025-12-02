# -*- coding: utf-8 -*-
"""
Миграция данных: заполнение базовых компонентов LCP.
Создаёт категории и системные компоненты для палитры редактора.
"""

from django.db import migrations


def populate_base_components(apps, schema_editor):
    """Создаёт базовые категории и системные компоненты."""
    LcpComponentCategory = apps.get_model('lcp', 'LcpComponentCategory')
    LcpComponentTemplate = apps.get_model('lcp', 'LcpComponentTemplate')
    
    # Создаём категории
    layout_cat = LcpComponentCategory.objects.create(
        name='Макет',
        slug='layout',
        icon='Layout',
        order=10
    )
    
    basic_cat = LcpComponentCategory.objects.create(
        name='Базовые',
        slug='basic',
        icon='Box',
        order=20
    )
    
    forms_cat = LcpComponentCategory.objects.create(
        name='Формы',
        slug='forms',
        icon='FileText',
        order=30
    )
    
    # Layout компоненты
    LcpComponentTemplate.objects.create(
        name='Контейнер',
        component_type='Container',
        category=layout_cat,
        icon='Container',
        description='Базовый контейнер для группировки компонентов',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={},
        default_styles={},
        default_classes=['container'],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Строка',
        component_type='Row',
        category=layout_cat,
        icon='Rows',
        description='Строка для размещения колонок',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={},
        default_styles={},
        default_classes=['row'],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Колонка',
        component_type='Column',
        category=layout_cat,
        icon='Columns',
        description='Колонка для размещения компонентов',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={},
        default_styles={},
        default_classes=['col'],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Карточка',
        component_type='Card',
        category=layout_cat,
        icon='Square',
        description='Карточка для группировки контента',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={},
        default_styles={},
        default_classes=['card'],
        props_schema={}
    )
    
    # Basic компоненты
    LcpComponentTemplate.objects.create(
        name='Текст',
        component_type='Text',
        category=basic_cat,
        icon='Type',
        description='Текстовый блок',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={'text': 'Текст'},
        default_styles={},
        default_classes=[],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Заголовок',
        component_type='Heading',
        category=basic_cat,
        icon='Heading',
        description='Заголовок (H1-H6)',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={'text': 'Заголовок', 'level': 1},
        default_styles={},
        default_classes=[],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Кнопка',
        component_type='Button',
        category=basic_cat,
        icon='MousePointerClick',
        description='Кнопка для действий',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={'text': 'Кнопка', 'variant': 'primary'},
        default_styles={},
        default_classes=['btn', 'btn-primary'],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Изображение',
        component_type='Image',
        category=basic_cat,
        icon='Image',
        description='Изображение',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={'src': '', 'alt': ''},
        default_styles={},
        default_classes=[],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Иконка',
        component_type='Icon',
        category=basic_cat,
        icon='Star',
        description='Иконка Lucide',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={'name': 'Star', 'size': 24},
        default_styles={},
        default_classes=[],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Разделитель',
        component_type='Divider',
        category=basic_cat,
        icon='Minus',
        description='Горизонтальный разделитель',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={},
        default_styles={},
        default_classes=[],
        props_schema={}
    )
    
    # Forms компоненты
    LcpComponentTemplate.objects.create(
        name='Поле ввода',
        component_type='Input',
        category=forms_cat,
        icon='Input',
        description='Текстовое поле ввода',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={'type': 'text', 'placeholder': 'Введите текст'},
        default_styles={},
        default_classes=['form-control'],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Выпадающий список',
        component_type='Select',
        category=forms_cat,
        icon='ChevronDown',
        description='Выпадающий список выбора',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={'options': [], 'placeholder': 'Выберите...'},
        default_styles={},
        default_classes=['form-select'],
        props_schema={}
    )
    
    LcpComponentTemplate.objects.create(
        name='Чекбокс',
        component_type='Checkbox',
        category=forms_cat,
        icon='CheckSquare',
        description='Чекбокс для выбора',
        is_system=True,
        is_global=True,
        is_active=True,
        default_props={'label': 'Чекбокс', 'checked': False},
        default_styles={},
        default_classes=['form-check-input'],
        props_schema={}
    )


def reverse_populate_base_components(apps, schema_editor):
    """Удаляет базовые компоненты и категории."""
    LcpComponentCategory = apps.get_model('lcp', 'LcpComponentCategory')
    LcpComponentTemplate = apps.get_model('lcp', 'LcpComponentTemplate')
    
    LcpComponentTemplate.objects.filter(is_system=True).delete()
    LcpComponentCategory.objects.filter(slug__in=['layout', 'basic', 'forms']).delete()


class Migration(migrations.Migration):
    
    dependencies = [
        ('lcp', '0002_populate_lcp_menu'),
    ]
    
    operations = [
        migrations.RunPython(
            populate_base_components,
            reverse_populate_base_components
        ),
    ]


