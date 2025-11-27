# Generated manually for Role inheritance from Group

import django.db.models.deletion
import django.contrib.auth.models
from django.conf import settings
from django.db import migrations, models


def create_system_roles(apps, schema_editor):
    """
    Создаёт базовые системные роли: 'Пользователь' и 'Администратор'.
    Использует SQL для корректной работы с наследованием от Group.
    """
    from django.db import connection
    
    roles_to_create = [
        ('Пользователь', 'Роль по умолчанию для всех пользователей', True),
        ('Администратор', 'Системная роль с полным доступом', True),
    ]
    
    with connection.cursor() as cursor:
        for name, description, is_system in roles_to_create:
            # Проверяем, существует ли уже Group с таким именем
            cursor.execute("SELECT id FROM auth_group WHERE name = %s", [name])
            row = cursor.fetchone()
            
            if row:
                group_id = row[0]
            else:
                # Создаём Group
                cursor.execute(
                    "INSERT INTO auth_group (name) VALUES (%s) RETURNING id",
                    [name]
                )
                group_id = cursor.fetchone()[0]
            
            # Проверяем, существует ли Role
            cursor.execute(
                "SELECT group_ptr_id FROM cms_adp_role WHERE group_ptr_id = %s",
                [group_id]
            )
            if not cursor.fetchone():
                # Создаём Role
                cursor.execute("""
                    INSERT INTO cms_adp_role (group_ptr_id, description, is_system, created_at, updated_at)
                    VALUES (%s, %s, %s, NOW(), NOW())
                """, [group_id, description, is_system])
            else:
                # Обновляем is_system, если роль уже существует
                cursor.execute("""
                    UPDATE cms_adp_role 
                    SET is_system = %s, description = %s, updated_at = NOW()
                    WHERE group_ptr_id = %s
                """, [is_system, description, group_id])


def delete_system_roles(apps, schema_editor):
    """Обратная миграция - удаляем системные роли."""
    from django.db import connection
    
    with connection.cursor() as cursor:
        for name in ['Пользователь', 'Администратор']:
            cursor.execute("SELECT id FROM auth_group WHERE name = %s", [name])
            row = cursor.fetchone()
            if row:
                cursor.execute("DELETE FROM cms_adp_role WHERE group_ptr_id = %s", [row[0]])


class Migration(migrations.Migration):

    dependencies = [
        ('auth', '0012_alter_user_first_name_max_length'),
        ('cms_adp', '0003_userprofile'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                ('group_ptr', models.OneToOneField(auto_created=True, on_delete=django.db.models.deletion.CASCADE, parent_link=True, primary_key=True, serialize=False, to='auth.group')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Описание')),
                ('is_system', models.BooleanField(default=False, verbose_name='Системная роль')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Роль',
                'verbose_name_plural': 'Роли',
                'ordering': ['name'],
            },
            bases=('auth.group',),
        ),
        migrations.CreateModel(
            name='RoleGroup',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, verbose_name='Название группы')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('parent_role', models.ForeignKey(limit_choices_to={'is_system': False}, on_delete=django.db.models.deletion.CASCADE, related_name='role_groups', to='cms_adp.role', verbose_name='Родительская роль')),
            ],
            options={
                'verbose_name': 'Ролевая группа',
                'verbose_name_plural': 'Ролевые группы',
                'ordering': ['name'],
                'unique_together': {('name', 'parent_role')},
            },
        ),
        migrations.CreateModel(
            name='Policy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Название политики')),
                ('policy_type', models.CharField(choices=[('url', 'Доступ к URL'), ('component', 'Доступ к компоненту')], default='url', max_length=20, verbose_name='Тип политики')),
                ('action', models.CharField(choices=[('allow', 'Разрешить'), ('deny', 'Запретить')], default='allow', max_length=10, verbose_name='Действие')),
                ('resource_path', models.CharField(max_length=500, verbose_name='Путь к ресурсу')),
                ('is_pattern', models.BooleanField(default=False, verbose_name='Использовать шаблон')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Описание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('priority', models.IntegerField(default=0, verbose_name='Приоритет')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('role', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='policies', to='cms_adp.role', verbose_name='Роль')),
                ('role_group', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='policies', to='cms_adp.rolegroup', verbose_name='Ролевая группа')),
            ],
            options={
                'verbose_name': 'Политика',
                'verbose_name_plural': 'Политики',
                'ordering': ['-priority', 'name'],
            },
        ),
        migrations.CreateModel(
            name='UserRole',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('assigned_at', models.DateTimeField(auto_now_add=True, verbose_name='Дата назначения')),
                ('assigned_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='role_assignments_made', to=settings.AUTH_USER_MODEL, verbose_name='Назначил')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_assignments', to='cms_adp.role', verbose_name='Роль')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_roles', to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'verbose_name': 'Роль пользователя',
                'verbose_name_plural': 'Роли пользователей',
                'unique_together': {('user', 'role')},
            },
        ),
        migrations.CreateModel(
            name='ModulePermission',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('module_name', models.CharField(max_length=100, verbose_name='Название модуля')),
                ('permission_key', models.CharField(max_length=100, verbose_name='Ключ разрешения')),
                ('permission_name', models.CharField(max_length=200, verbose_name='Название разрешения')),
                ('description', models.TextField(blank=True, null=True, verbose_name='Описание')),
                ('is_granted', models.BooleanField(default=False, verbose_name='Предоставлено')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('role_group', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='module_permissions', to='cms_adp.rolegroup', verbose_name='Ролевая группа')),
            ],
            options={
                'verbose_name': 'Разрешение модуля',
                'verbose_name_plural': 'Разрешения модулей',
                'unique_together': {('module_name', 'permission_key', 'role_group')},
                'ordering': ['module_name', 'permission_key'],
            },
        ),
        migrations.AddField(
            model_name='userrole',
            name='role_groups',
            field=models.ManyToManyField(blank=True, related_name='user_assignments', to='cms_adp.rolegroup', verbose_name='Ролевые группы'),
        ),
        migrations.AlterModelManagers(
            name='role',
            managers=[
                ('objects', django.contrib.auth.models.GroupManager()),
            ],
        ),
        migrations.RunPython(
            create_system_roles,
            delete_system_roles,
        ),
    ]

