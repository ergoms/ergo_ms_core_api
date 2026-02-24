# -*- coding: utf-8 -*-
"""
Миграция данных: добавление меню модуля Neural Networks Hub (Модуль нейронных сетей).
Ролевые группы «Преподаватель (НН)» и «Студент (НН)» привязаны к роли «Пользователь».
Пункты меню фильтруются по allowed_role_groups: преподаватель и студент видят только свои пункты.
"""

from django.db import migrations

# Имена ролевых групп для фильтрации меню
ROLE_GROUP_TEACHER = 'Преподаватель (НН)'
ROLE_GROUP_STUDENT = 'Студент (НН)'


def add_neural_networks_hub_menu(apps, schema_editor):
    """Создаёт ролевые группы, элементы меню и привязывает пункты к ролям."""
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper

    Role = apps.get_model('cms_adp', 'Role')
    RoleGroup = apps.get_model('cms_adp', 'RoleGroup')
    MenuItem = apps.get_model('cms_adp', 'MenuItem')

    # Ролевые группы под ролью «Пользователь» (для фильтрации меню)
    role_user = Role.objects.filter(name='Пользователь').first()
    if not role_user:
        return
    teacher_group, _ = RoleGroup.objects.get_or_create(
        name=ROLE_GROUP_TEACHER,
        parent_role=role_user,
        defaults={'description': 'Преподаватель в модуле нейронных сетей', 'is_active': True},
    )
    student_group, _ = RoleGroup.objects.get_or_create(
        name=ROLE_GROUP_STUDENT,
        parent_role=role_user,
        defaults={'description': 'Студент в модуле нейронных сетей', 'is_active': True},
    )

    helper = MenuMigrationHelper(apps, 'modules/neural_networks_hub')
    helper.clear_module_items()

    root = helper.create_group(
        'Модуль нейронных сетей', 'NeuralNetworksHub', icon='Brain'
    )

    # Видят все (до выбора роли): только выбор роли
    helper.create_route('Выбор роли', 'NNHubRoleSelect', parent=root, icon='UserPlus')

    # Курсы видны только после выбора роли (преподаватель или студент)
    r_courses = helper.create_route('Курсы', 'NNHubCourseList', parent=root)
    r_courses.allowed_role_groups.add(teacher_group)
    r_courses.allowed_role_groups.add(student_group)

    # Только преподаватель (allowed_role_groups задаём после создания)
    r_teacher = helper.create_route('Рабочее место', 'NNHubTeacher', parent=root, icon='GraduationCap')
    r_groups = helper.create_route('Учебные группы', 'NNHubGroups', parent=root)
    r_teacher.allowed_role_groups.add(teacher_group)
    r_groups.allowed_role_groups.add(teacher_group)

    # Только студент
    r_student = helper.create_route('Рабочее место', 'NNHubStudent', parent=root, icon='User')
    r_my = helper.create_route('Мои курсы', 'NNHubMyEnrollments', parent=root)
    r_student.allowed_role_groups.add(student_group)
    r_my.allowed_role_groups.add(student_group)

    # Мониторинг RAG — только преподаватель
    eval_group = helper.create_group(
        'Мониторинг RAG', 'NNHubEvalDashboard', icon='BarChart2', parent=root
    )
    eval_group.allowed_role_groups.add(teacher_group)
    r_eval_dash = helper.create_route('Дашборд', 'NNHubEvalDashboard', parent=eval_group)
    r_eval_ds = helper.create_route('Эталонные датасеты', 'NNHubEvalDatasets', parent=eval_group)
    r_eval_exp = helper.create_route('Эксперименты', 'NNHubExperiments', parent=eval_group)
    for item in (r_eval_dash, r_eval_ds, r_eval_exp):
        item.allowed_role_groups.add(teacher_group)


def remove_neural_networks_hub_menu(apps, schema_editor):
    """Удаляет элементы меню и ролевые группы модуля neural_networks_hub."""
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    RoleGroup = apps.get_model('cms_adp', 'RoleGroup')
    MenuItem.objects.filter(module_source='modules/neural_networks_hub').delete()
    RoleGroup.objects.filter(name__in=[ROLE_GROUP_TEACHER, ROLE_GROUP_STUDENT]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0009_add_theme_editor_menu'),
    ]

    operations = [
        migrations.RunPython(
            add_neural_networks_hub_menu,
            remove_neural_networks_hub_menu
        ),
    ]
