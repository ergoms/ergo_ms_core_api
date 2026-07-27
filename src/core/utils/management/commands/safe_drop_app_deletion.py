"""
Команда для безопасного удаления приложения Django.

Процесс:
1. Проверяет зависимости других приложений (ForeignKey, ManyToMany) на модели
2. Проверяет зависимости миграций
3. Показывает статистику (таблицы, записи, файлы миграций)
4. Удаляет данные, таблицы, записи из django_migrations и файлы миграций
"""
import re
from pathlib import Path
from collections import defaultdict

from django.apps import apps
from django.db import connection, DEFAULT_DB_ALIAS
from django.db.migrations.loader import MigrationLoader
from django.core.management.base import BaseCommand, CommandError


class SafeDropAppDeletionMixin:
    def _perform_deletion(
        self, 
        app_label, 
        models_info, 
        migrations_dir,
        keep_migrations,
        cascade,
        migration_dependencies
    ):
        """Выполняет удаление."""
        self.stdout.write('\n' + '=' * 60)
        self.stdout.write(self.style.MIGRATE_HEADING('Выполнение удаления...'))
        self.stdout.write('=' * 60)

        # 1. Обновляем зависимости миграций в других приложениях
        if migration_dependencies:
            self._update_migration_dependencies(app_label, migration_dependencies)

        # 2. Удаляем таблицы (в обратном порядке зависимостей)
        self._drop_tables(models_info, cascade)

        # 3. Удаляем записи из django_migrations
        self._delete_migration_records(app_label)

        # 4. Удаляем файлы миграций
        if not keep_migrations and migrations_dir.exists():
            self._delete_migration_files(migrations_dir)

    def _fix_migration_dependencies(self, app_label, dependencies):
        """
        Исправляет зависимости миграций ДО создания новых миграций.
        1. Удаляет ссылки на удаляемое приложение из файлов миграций
        2. Удаляет записи из django_migrations для сломанных миграций
           (иначе Django будет ругаться на несуществующие зависимости)
        """
        self.stdout.write('\nИсправление зависимостей миграций...')
        
        fixed = 0
        migrations_to_reset = []
        
        for dep in dependencies:
            try:
                other_app_config = apps.get_app_config(dep['app'])
                migration_file = (
                    Path(other_app_config.path) / 
                    'migrations' / 
                    f'{dep["migration"]}.py'
                )
                
                if not migration_file.exists():
                    self.stdout.write(self.style.WARNING(
                        f'Файл не найден: {migration_file}'
                    ))
                    continue
                
                with open(migration_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                # Удаляем зависимость на наше приложение
                # Паттерн: ('app_label', 'migration_name'),
                pattern = rf"\(\s*['\"]?{re.escape(app_label)}['\"]?\s*,\s*['\"][^'\"]+['\"]\s*\)\s*,?\s*\n?"
                content = re.sub(pattern, '', content)
                
                if content != original_content:
                    with open(migration_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    fixed += 1
                    migrations_to_reset.append((dep['app'], dep['migration']))
                    self.stdout.write(self.style.SUCCESS(
                        f'Удалена зависимость из {dep["app"]}.{dep["migration"]}'
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'Зависимость не найдена в файле {dep["app"]}.{dep["migration"]}'
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Ошибка при исправлении {dep["app"]}.{dep["migration"]}: {e}'
                ))
        
        # ВАЖНО: Удаляем записи из django_migrations для исправленных миграций
        # Это необходимо, потому что Django кеширует зависимости и будет ругаться
        # на несуществующую зависимость settings.XXXX даже после изменения файла
        if migrations_to_reset:
            self.stdout.write('\nСброс записей миграций в django_migrations...')
            for app, migration in migrations_to_reset:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                            [app, migration]
                        )
                        if cursor.rowcount > 0:
                            self.stdout.write(self.style.SUCCESS(
                                f'Удалена запись {app}.{migration}'
                            ))
                        else:
                            self.stdout.write(
                                f' ℹ Запись {app}.{migration} не найдена в БД'
                            )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'Ошибка при удалении записи {app}.{migration}: {e}'
                    ))
        
        # Также чистим ВСЕ миграции затронутых приложений от ссылок на удаляемое приложение
        # (не только dependencies, но и операции AddField, CreateModel и т.д.)
        affected_apps = set(dep['app'] for dep in dependencies)
        for affected_app in affected_apps:
            self._clean_all_migrations_from_app_refs(affected_app, app_label)
        
        if fixed > 0:
            self.stdout.write(self.style.SUCCESS(f'\nИсправлено миграций: {fixed}'))
        
        return fixed

    def _clean_all_migrations_from_app_refs(self, affected_app, removed_app):
        """
        Удаляет файлы миграций affected_app, которые содержат ссылки на removed_app.
        
        Редактирование миграций regex'ами ненадёжно и ломает синтаксис Python.
        Безопаснее удалить миграции и создать новые.
        """
        try:
            app_config = apps.get_app_config(affected_app)
            migrations_dir = Path(app_config.path) / 'migrations'
            
            if not migrations_dir.exists():
                return
            
            self.stdout.write(f'\nПоиск миграций {affected_app} со ссылками на {removed_app}...')
            
            migrations_to_delete = []
            
            for migration_file in migrations_dir.glob('*.py'):
                if migration_file.name == '__init__.py':
                    continue
                
                try:
                    with open(migration_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Проверяем, есть ли ссылки на removed_app
                    has_refs = (
                        f"'{removed_app}."in content or 
                        f'"{removed_app}.'in content or
                        f"'{removed_app}',"in content or
                        f'"{removed_app}",'in content
                    )
                    
                    if has_refs:
                        migrations_to_delete.append(migration_file)
                        
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'Ошибка при проверке {migration_file.name}: {e}'
                    ))
            
            if not migrations_to_delete:
                self.stdout.write('Миграции со ссылками не найдены')
                return
            
            self.stdout.write(f'\nУдаление {len(migrations_to_delete)} миграций со ссылками на {removed_app}...')
            
            for migration_file in migrations_to_delete:
                migration_name = migration_file.stem
                
                # Удаляем запись из django_migrations
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                            [affected_app, migration_name]
                        )
                        if cursor.rowcount > 0:
                            self.stdout.write(f'Удалена запись из БД: {migration_name}')
                except Exception:
                    pass
                
                # Удаляем файл
                try:
                    migration_file.unlink()
                    self.stdout.write(f'Удалён файл: {migration_file.name}')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'Ошибка при удалении {migration_file.name}: {e}'
                    ))
            
            self.stdout.write(self.style.SUCCESS(
                f'Удалено миграций: {len(migrations_to_delete)}'
            ))
                
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'Ошибка при очистке миграций {affected_app}: {e}'
            ))

    def _update_migration_dependencies(self, app_label, dependencies):
        """Обновляет зависимости в миграциях других приложений (при удалении)."""
        self.stdout.write('\nОбновление зависимостей миграций...')
        
        updated = 0
        for dep in dependencies:
            try:
                other_app_config = apps.get_app_config(dep['app'])
                migration_file = (
                    Path(other_app_config.path) / 
                    'migrations' / 
                    f'{dep["migration"]}.py'
                )
                
                if not migration_file.exists():
                    continue
                
                with open(migration_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Удаляем зависимость на наше приложение
                pattern = rf"\(\s*['\"]?{re.escape(app_label)}['\"]?\s*,\s*['\"][^'\"]+['\"]\s*\)\s*,?\s*\n?"
                new_content = re.sub(pattern, '', content)
                
                if new_content != content:
                    with open(migration_file, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    updated += 1
                    self.stdout.write(f' {dep["app"]}.{dep["migration"]}')
                    
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Ошибка при обновлении {dep["app"]}.{dep["migration"]}: {e}'
                ))
        
        self.stdout.write(f'Обновлено миграций: {updated}')

    def _drop_tables(self, models_info, cascade):
        """Удаляет таблицы из БД."""
        self.stdout.write('\nУдаление таблиц...')
        
        # Сортируем таблицы в порядке, учитывающем зависимости
        # (таблицы с FK на другие таблицы удаляем первыми)
        sorted_models = self._sort_models_by_dependencies(models_info)
        
        dropped = 0
        for model_info in sorted_models:
            table = model_info['table']
            try:
                with connection.cursor() as cursor:
                    if cascade:
                        cursor.execute(
                            f"DROP TABLE IF EXISTS {connection.ops.quote_name(table)} CASCADE"
                        )
                    else:
                        cursor.execute(
                            f"DROP TABLE IF EXISTS {connection.ops.quote_name(table)}"
                        )
                dropped += 1
                self.stdout.write(f' {table}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Ошибка при удалении {table}: {e}'
                ))
        
        self.stdout.write(f'Удалено таблиц: {dropped}')

    def _sort_models_by_dependencies(self, models_info):
        """Сортирует модели по зависимостям (FK) для правильного порядка удаления.
        
        M2M таблицы удаляются первыми, так как они имеют FK на основные таблицы.
        """
        # Разделяем на M2M и обычные модели
        m2m_models = [m for m in models_info if m.get('is_m2m')]
        regular_models = [m for m in models_info if not m.get('is_m2m')]
        
        # Строим граф зависимостей для обычных моделей
        our_tables = {m['table']: m for m in regular_models}
        dependencies = defaultdict(set)
        
        for model_info in regular_models:
            model = model_info.get('model')
            if not model:
                continue
            for field in model._meta.get_fields():
                if hasattr(field, 'related_model') and field.related_model:
                    related_table = field.related_model._meta.db_table
                    if related_table in our_tables and related_table != model_info['table']:
                        # Наша таблица зависит от related_table
                        dependencies[model_info['table']].add(related_table)
        
        # Топологическая сортировка (зависимые таблицы первыми)
        sorted_tables = []
        visited = set()
        
        def visit(table):
            if table in visited:
                return
            visited.add(table)
            for dep in dependencies[table]:
                visit(dep)
            sorted_tables.append(table)
        
        for model_info in regular_models:
            visit(model_info['table'])
        
        # Возвращаем в обратном порядке (сначала зависимые)
        sorted_tables.reverse()
        sorted_regular = [our_tables[t] for t in sorted_tables if t in our_tables]
        
        # M2M таблицы удаляем первыми (они имеют FK на основные таблицы)
        return m2m_models + sorted_regular

    def _delete_migration_records(self, app_label):
        """Удаляет записи из django_migrations."""
        self.stdout.write('\nУдаление записей из django_migrations...')
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM django_migrations WHERE app = %s",
                    [app_label]
                )
                deleted = cursor.rowcount
            self.stdout.write(f'Удалено записей: {deleted}')
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'Ошибка при удалении записей: {e}'
            ))

    def _delete_migration_files(self, migrations_dir):
        """Удаляет файлы миграций."""
        self.stdout.write('\nУдаление файлов миграций...')
        
        deleted = 0
        for migration_file in migrations_dir.glob('*.py'):
            if migration_file.name == '__init__.py':
                continue
            try:
                migration_file.unlink()
                deleted += 1
                self.stdout.write(f' {migration_file.name}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Ошибка при удалении {migration_file.name}: {e}'
                ))
        
        self.stdout.write(f'Удалено файлов: {deleted}')

    def _auto_fix_dependencies(self, app_label, model_dependencies):
        """
        Автоматически удаляет ссылающиеся поля из других моделей.
        Возвращает список приложений, которые были изменены.
        """
        fixed_apps = set()
        all_deps = (
            model_dependencies['foreign_keys'] + 
            model_dependencies['many_to_many'] + 
            model_dependencies['one_to_one']
        )
        
        # Группируем зависимости по файлам моделей
        files_to_fix = defaultdict(list)
        for dep in all_deps:
            try:
                other_app_config = apps.get_app_config(dep['app'])
                models_file = Path(other_app_config.path) / 'models.py'
                if models_file.exists():
                    files_to_fix[models_file].append(dep)
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Не удалось найти приложение {dep["app"]}: {e}'
                ))
        
        for models_file, deps in files_to_fix.items():
            try:
                with open(models_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                original_content = content
                
                for dep in deps:
                    field_name = dep['field']
                    model_name = dep['model']
                    
                    # Удаляем определение поля из модели
                    content = self._remove_field_from_model(
                        content, model_name, field_name
                    )
                
                if content != original_content:
                    with open(models_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    app_label_fixed = deps[0]['app']
                    fixed_apps.add(app_label_fixed)
                    
                    for dep in deps:
                        self.stdout.write(self.style.SUCCESS(
                            f'Удалено поле {dep["model"]}.{dep["field"]} '
                            f'из {models_file.name}'
                        ))
                        
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Ошибка при обработке {models_file}: {e}'
                ))
        
        return fixed_apps

    def _remove_field_from_model(self, content, model_name, field_name):
        """
        Удаляет определение поля из содержимого файла модели.
        Поддерживает однострочные и многострочные определения полей.
        """
        # Паттерн для однострочного поля: field_name = models.FieldType(...)
        single_line_pattern = rf'^(\s*){re.escape(field_name)}\s*=\s*models\.\w+\([^)]*\)\s*$'
        
        # Паттерн для многострочного поля (с переносами внутри скобок)
        # Ищем начало определения поля
        multi_line_start = rf'^(\s*){re.escape(field_name)}\s*=\s*models\.\w+\('
        
        lines = content.split('\n')
        new_lines = []
        skip_until_close = False
        paren_depth = 0
        indent_to_match = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            if skip_until_close:
                # Считаем скобки
                paren_depth += line.count('(') - line.count(')')
                if paren_depth <= 0:
                    skip_until_close = False
                    paren_depth = 0
                i += 1
                continue
            
            # Проверяем однострочное определение
            if re.match(single_line_pattern, line, re.MULTILINE):
                i += 1
                continue
            
            # Проверяем начало многострочного определения
            if re.match(multi_line_start, line):
                paren_depth = line.count('(') - line.count(')')
                if paren_depth > 0:
                    skip_until_close = True
                i += 1
                continue
            
            new_lines.append(line)
            i += 1
        
        return '\n'.join(new_lines)

    def _create_migrations_for_apps(self, app_labels):
        """Создаёт миграции для указанных приложений."""
        from django.core.management import call_command
        
        self.stdout.write('\nСоздание миграций для изменённых приложений...')
        
        for app_label in app_labels:
            try:
                self.stdout.write(f'Создание миграций для {app_label}...')
                call_command('makemigrations', app_label, verbosity=0)
                self.stdout.write(self.style.SUCCESS(f' {app_label}'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'Ошибка при создании миграций для {app_label}: {e}'
                ))

    def _apply_migrations(self):
        """Применяет все миграции."""
        from django.core.management import call_command
        
        self.stdout.write('\nПрименение миграций...')
        
        try:
            call_command('migrate', verbosity=0)
            self.stdout.write(self.style.SUCCESS('Миграции применены'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'Ошибка при применении миграций: {e}'
            ))

