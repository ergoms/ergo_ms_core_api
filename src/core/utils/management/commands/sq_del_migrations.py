"""
Команда для объединения миграций с проверкой зависимостей.

Процесс:
1. Создает squash миграцию через squashmigrations
2. Проверяет зависимости других приложений на старые миграции
3. Удаляет старые миграции только если нет зависимостей
4. Обновляет зависимости в других приложениях при необходимости
"""
import os
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = (
        'Объединяет миграции приложения через squash и удаляет старые файлы. '
        'Проверяет зависимости других приложений перед удалением.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'app_label',
            type=str,
            help='Название приложения (например, cms_shortcodes)'
        )
        parser.add_argument(
            'start_migration',
            type=str,
            nargs='?',
            help='Начальная миграция для объединения (по умолчанию 0001_initial). Если не указана, используется первая миграция.'
        )
        parser.add_argument(
            'end_migration',
            type=str,
            nargs='?',
            help='Конечная миграция для объединения (по умолчанию последняя миграция приложения)'
        )
        parser.add_argument(
            '--noinput',
            '--no-input',
            action='store_false',
            dest='interactive',
            help='Не запрашивать подтверждение у пользователя',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Принудительно удалить миграции даже при наличии зависимостей',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Только проверить зависимости, не выполнять squash',
        )

    def handle(self, *args, **options):
        app_label = options['app_label']
        start_migration = options.get('start_migration')
        end_migration = options.get('end_migration')
        interactive = options.get('interactive', True)
        force = options.get('force', False)
        check_only = options.get('check_only', False)

        # Проверяем, существует ли приложение
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            raise CommandError(f'Приложение "{app_label}" не найдено.')

        app_path = Path(app_config.path)
        migrations_dir = app_path / 'migrations'

        if not migrations_dir.exists():
            raise CommandError(
                f'Директория migrations не найдена для приложения "{app_label}"'
            )

        # Загружаем все миграции для проверки зависимостей
        from django.db import connections, DEFAULT_DB_ALIAS
        loader = MigrationLoader(connections[DEFAULT_DB_ALIAS])
        
        # Получаем все миграции приложения через graph.nodes
        app_migrations = {}
        for (app, name), migration in loader.graph.nodes.items():
            if app == app_label:
                app_migrations[name] = migration
        
        if not app_migrations:
            raise CommandError(
                f'Миграции не найдены для приложения "{app_label}"'
            )
        
        # Определяем начальную миграцию
        if not start_migration:
            # Находим первую миграцию (обычно 0001_initial)
            migration_names = sorted(app_migrations.keys())
            start_migration = migration_names[0]
            self.stdout.write(
                f'Начальная миграция не указана, используется: {start_migration}'
            )
        
        # Определяем конечную миграцию (последняя, если не указана)
        if not end_migration:
            # Находим последнюю миграцию приложения через graph.leaf_nodes()
            # Листовые узлы - это миграции, от которых не зависят другие миграции
            leaf_nodes = loader.graph.leaf_nodes()
            app_leaf_nodes = [name for app, name in leaf_nodes if app == app_label]
            
            if app_leaf_nodes:
                # Если несколько листовых миграций, берем последнюю по имени (обычно самая новая)
                # Но лучше проверить через graph - какая из них действительно последняя
                last_migration = None
                max_depth = -1
                for leaf_name in app_leaf_nodes:
                    try:
                        plan = loader.graph.backwards_plan((app_label, leaf_name))
                        depth = len([m for m in plan if m[0] == app_label])
                        if depth > max_depth:
                            max_depth = depth
                            last_migration = leaf_name
                    except:
                        pass
                
                if last_migration:
                    end_migration = last_migration
                else:
                    # Fallback: берем последнюю по имени
                    end_migration = sorted(app_leaf_nodes)[-1]
            else:
                # Если не нашли листовые, берем последнюю по имени из всех миграций
                end_migration = sorted(app_migrations.keys())[-1]
            
            self.stdout.write(
                f'Конечная миграция не указана, используется последняя: {end_migration}'
            )

        # Проверяем зависимости других приложений
        migrations_to_squash = []
        dependencies_found = []
        
        # Определяем диапазон миграций для объединения через graph
        try:
            # Получаем все миграции между start и end через graph
            plan = loader.graph.forwards_plan((app_label, end_migration))
            
            in_range = False
            for app, name in plan:
                if app == app_label:
                    if name == start_migration:
                        in_range = True
                    if in_range:
                        migrations_to_squash.append(name)
                    if name == end_migration:
                        break
        except Exception as e:
            raise CommandError(
                f'Ошибка при определении миграций для объединения: {e}'
            )
        
        if not migrations_to_squash:
            raise CommandError(
                f'Не найдены миграции для объединения между "{start_migration}" и "{end_migration}"'
            )
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Найдено миграций для объединения: {len(migrations_to_squash)}'
            )
        )
        self.stdout.write(f'От: {migrations_to_squash[0]}')
        self.stdout.write(f'До: {migrations_to_squash[-1]}')

        # Проверяем зависимости других приложений
        self.stdout.write('\nПроверка зависимостей других приложений...')
        
        # Проходим по всем миграциям в graph
        for (app_name, migration_name), migration in loader.graph.nodes.items():
            if app_name == app_label:
                continue
            
            # Проверяем dependencies
            for dep_app, dep_name in migration.dependencies:
                if dep_app == app_label and dep_name in migrations_to_squash:
                    dependencies_found.append({
                        'app': app_name,
                        'migration': migration_name,
                        'depends_on': (app_label, dep_name),
                        'type': 'dependency'
                    })
            
            # Проверяем run_before
            for dep_app, dep_name in getattr(migration, 'run_before', []):
                if dep_app == app_label and dep_name in migrations_to_squash:
                    dependencies_found.append({
                        'app': app_name,
                        'migration': migration_name,
                        'depends_on': (app_label, dep_name),
                        'type': 'run_before'
                    })

        # Собираем статистику для отображения
        stats = self._collect_statistics(
            app_label, migrations_to_squash, loader, migrations_dir
        )
        
        # Выводим статистику
        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.MIGRATE_HEADING('Статистика операции:'))
        self.stdout.write('='*60)
        
        self.stdout.write(f'\nФайлов миграций для удаления: {stats["migration_files_count"]}')
        if stats['migration_files']:
            for file_name in stats['migration_files'][:10]: # Показываем первые 10
                self.stdout.write(f' - {file_name}')
            if len(stats['migration_files']) > 10:
                self.stdout.write(f' ... и еще {len(stats["migration_files"]) - 10} файлов')
        
        self.stdout.write(f'\nЗаписей в django_migrations для удаления: {stats["db_records_count"]}')
        if stats['db_records']:
            for record in stats['db_records'][:10]: # Показываем первые 10
                self.stdout.write(f' - {record}')
            if len(stats['db_records']) > 10:
                self.stdout.write(f' ... и еще {len(stats["db_records"]) - 10} записей')
        
        self.stdout.write(f'\nТаблиц в БД (не будут удалены): {stats["tables_count"]}')
        if stats['tables']:
            for table in stats['tables'][:10]: # Показываем первые 10
                self.stdout.write(f' - {table}')
            if len(stats['tables']) > 10:
                self.stdout.write(f' ... и еще {len(stats["tables"]) - 10} таблиц')
        
        self.stdout.write('='*60)
        
        if dependencies_found:
            self.stdout.write(
                self.style.WARNING(
                    f'\nНайдено зависимостей от объединяемых миграций: {len(dependencies_found)}'
                )
            )
            for dep in dependencies_found:
                self.stdout.write(
                    f" {dep['app']}.{dep['migration']} "
                    f"({dep['type']}) -> {dep['depends_on'][0]}.{dep['depends_on'][1]}"
                )
            self.stdout.write(
                '\nDjango автоматически обновит зависимости при применении squash миграции.'
            )
        
        if not check_only:
            if interactive:
                self.stdout.write(
                    self.style.WARNING(
                        '\nВНИМАНИЕ: Эта операция удалит файлы миграций и записи из БД!'
                    )
                )
                response = input('\nПродолжить? (yes/no): ')
                if response.lower() not in ('yes', 'y'):
                    self.stdout.write(self.style.ERROR('Отменено пользователем.'))
                    return
            else:
                self.stdout.write(
                    self.style.WARNING(
                        '\nПродолжаем с автоматическим обновлением зависимостей...'
                    )
                )

        if check_only:
            self.stdout.write(
                self.style.SUCCESS('\nПроверка завершена. Используйте без --check-only для выполнения.')
            )
            return

        # Выполняем squash
        self.stdout.write('\nСоздание squash миграции...')
        try:
            # Формируем аргументы для squashmigrations
            squash_args = [app_label]
            if start_migration:
                squash_args.append(start_migration)
            squash_args.append(end_migration)
            
            call_command(
                'squashmigrations',
                *squash_args,
                verbosity=options.get('verbosity', 1),
                no_input=not interactive,
            )
            self.stdout.write(
                self.style.SUCCESS('Squash миграция успешно создана.')
            )
        except Exception as e:
            raise CommandError(f'Ошибка при создании squash миграции: {e}')

        # Находим созданную squash миграцию
        # Получаем список существующих миграций для сравнения
        existing_migrations = set([
            f.stem for f in migrations_dir.glob('*.py')
            if f.name != '__init__.py'and not f.name.startswith('.')
        ])
        
        squash_files = list(migrations_dir.glob('*_squashed_*.py'))
        if not squash_files:
            # Может быть создана миграция с другим именем (не squashed)
            # Ищем файлы, которых не было в исходном списке
            all_files = set([
                f.stem for f in migrations_dir.glob('*.py')
                if f.name != '__init__.py'and not f.name.startswith('.')
            ])
            new_files = all_files - existing_migrations
            if new_files:
                squash_files = [migrations_dir / f'{name}.py'for name in new_files]
        
        if not squash_files:
            self.stdout.write(
                self.style.WARNING(
                    'Squash миграция не найдена. Возможно, она уже существует или произошла ошибка.'
                )
            )
            return

        squash_file = squash_files[0]
        self.stdout.write(f'Найдена squash миграция: {squash_file.name}')

        # Автоматически исправляем функции RunPython, если они требуют manual porting
        self._fix_runpython_functions(squash_file, migrations_to_squash, app_label, loader)
        
        # Автоматически обновляем зависимости в других приложениях
        self._update_dependencies_in_other_apps(
            app_label, migrations_to_squash, squash_file.stem, loader
        )

        # Удаляем записи из django_migrations БЕЗОПАСНО
        self.stdout.write('\nУдаление записей из django_migrations...')
        from django.db import connection
        from django.db.migrations.recorder import MigrationRecorder
        
        deleted_db_records = 0
        with connection.cursor() as cursor:
            for migration_name in migrations_to_squash:
                # Пропускаем начальную миграцию, если она не в списке для удаления
                if migration_name == start_migration and start_migration.startswith('0001_'):
                    continue
                
                # Безопасно удаляем запись
                cursor.execute(
                    "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                    [app_label, migration_name]
                )
                if cursor.rowcount > 0:
                    deleted_db_records += 1
                    self.stdout.write(f'Удалена запись: {app_label}.{migration_name}')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Удалено записей из БД: {deleted_db_records}'
            )
        )
        
        # Удаляем старые файлы миграций
        self.stdout.write('\nУдаление старых файлов миграций...')
        deleted_count = 0
        
        for migration_name in migrations_to_squash:
            # Пропускаем начальную миграцию, если она не в списке для удаления
            if migration_name == start_migration and start_migration.startswith('0001_'):
                self.stdout.write(
                    f'Пропущена начальная миграция: {migration_name}'
                )
                continue
            
            migration_file = migrations_dir / f'{migration_name}.py'
            if migration_file.exists():
                migration_file.unlink()
                deleted_count += 1
                self.stdout.write(f'Удален файл: {migration_name}.py')
        
        self.stdout.write(
            self.style.SUCCESS(
                f'Удалено файлов миграций: {deleted_count}'
            )
        )
        
        self.stdout.write(
            self.style.SUCCESS(
                '\nОбъединение миграций завершено успешно!\n'
                'Следующие шаги:\n'
                '1. Проверьте созданную squash миграцию\n'
                '2. Примените миграции: python manage.py migrate\n'
                '3. После применения на всех инстансах можно удалить squash миграцию '
                'и оставить только объединенную'
            )
        )

    def _collect_statistics(self, app_label, migrations_to_squash, loader, migrations_dir):
        """
        Собирает статистику о миграциях, файлах и таблицах для отображения.
        """
        stats = {
            'migration_files': [],
            'migration_files_count': 0,
            'db_records': [],
            'db_records_count': 0,
            'tables': [],
            'tables_count': 0,
        }
        
        # Собираем список файлов миграций
        for migration_name in migrations_to_squash:
            migration_file = migrations_dir / f'{migration_name}.py'
            if migration_file.exists():
                stats['migration_files'].append(migration_name)
        stats['migration_files_count'] = len(stats['migration_files'])
        
        # Собираем список записей в django_migrations
        from django.db import connection, DEFAULT_DB_ALIAS
        with connection.cursor() as cursor:
            # Используем IN с кортежем для совместимости с PostgreSQL
            placeholders = ','.join(['%s'] * len(migrations_to_squash))
            cursor.execute(
                f"SELECT name FROM django_migrations WHERE app = %s AND name IN ({placeholders})",
                [app_label] + migrations_to_squash
            )
            stats['db_records'] = [row[0] for row in cursor.fetchall()]
        stats['db_records_count'] = len(stats['db_records'])
        
        # Собираем список таблиц приложения в БД напрямую из information_schema
        # Используем префикс приложения для поиска всех таблиц
        try:
            with connection.cursor() as cursor:
                # Ищем все таблицы, которые начинаются с префикса приложения
                # Например, для app_label='settings' ищем таблицы, начинающиеся с 'settings_'
                table_prefix = f"{app_label}_"
                cursor.execute(
                    """
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    AND table_name LIKE %s
                    ORDER BY table_name
                    """,
                    [f"{table_prefix}%"]
                )
                stats['tables'] = [row[0] for row in cursor.fetchall()]
        except Exception as e:
            # Если не удалось получить таблицы, просто пропускаем
            self.stdout.write(
                self.style.WARNING(f'Не удалось получить список таблиц: {e}')
            )
        
        stats['tables_count'] = len(stats['tables'])
        
        return stats

    def _update_dependencies_in_other_apps(self, app_label, replaced_migrations, squash_migration_name, loader):
        """
        Автоматически обновляет зависимости в других приложениях,
        заменяя ссылки на замененные миграции на новую squash миграцию.
        """
        import re
        
        self.stdout.write('\nОбновление зависимостей в других приложениях...')
        
        updated_count = 0
        
        # Проходим по всем миграциям в graph
        for (other_app, other_migration_name), other_migration in loader.graph.nodes.items():
            if other_app == app_label:
                continue
            
            # Проверяем dependencies
            needs_update = False
            new_dependencies = []
            
            for dep_app, dep_name in other_migration.dependencies:
                if dep_app == app_label and dep_name in replaced_migrations:
                    # Заменяем на squash миграцию
                    new_dependencies.append((app_label, squash_migration_name))
                    needs_update = True
                    self.stdout.write(
                        f'Найдена зависимость: {other_app}.{other_migration_name} -> {app_label}.{dep_name}'
                    )
                else:
                    new_dependencies.append((dep_app, dep_name))
            
            if needs_update:
                # Находим файл миграции
                try:
                    other_app_config = apps.get_app_config(other_app)
                    other_migrations_dir = Path(other_app_config.path) / 'migrations'
                    other_migration_file = other_migrations_dir / f'{other_migration_name}.py'
                    
                    if not other_migration_file.exists():
                        self.stdout.write(
                            self.style.WARNING(
                                f'Файл миграции не найден: {other_migration_file}'
                            )
                        )
                        continue
                    
                    # Читаем файл
                    with open(other_migration_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Заменяем зависимости
                    original_content = content
                    for replaced_migration in replaced_migrations:
                        # Ищем паттерн: ('app_label', 'replaced_migration')
                        pattern = rf"\(\s*['\"]{re.escape(app_label)}['\"]\s*,\s*['\"]{re.escape(replaced_migration)}['\"]\s*\)"
                        replacement = f"('{app_label}', '{squash_migration_name}')"
                        content = re.sub(pattern, replacement, content)
                    
                    # Если что-то изменилось, записываем обратно
                    if content != original_content:
                        with open(other_migration_file, 'w', encoding='utf-8') as f:
                            f.write(content)
                        updated_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(
                                f'Обновлена зависимость в {other_app}.{other_migration_name}'
                            )
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(
                                f'Не удалось найти зависимость в файле {other_migration_file}'
                            )
                        )
                        
                except Exception as e:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Ошибка при обновлении {other_app}.{other_migration_name}: {e}'
                        )
                    )
        
        if updated_count > 0:
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nОбновлено зависимостей в других приложениях: {updated_count}'
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    '\nЗависимости в других приложениях не требуют обновления'
                )
            )

    def _fix_runpython_functions(self, squash_file, migrations_to_squash, app_label, loader):
        """
        Автоматически копирует функции из RunPython операций в squash миграцию,
        если они находятся в модулях с именами, начинающимися с цифр.
        """
        import re
        import ast
        import inspect
        
        try:
            # Читаем содержимое squash миграции
            with open(squash_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Проверяем, есть ли упоминания о manual porting
            if '# Functions from the following migrations need manual copying'not in content:
                # Нет функций, требующих копирования
                return
            
            # Ищем все RunPython операции с проблемными импортами
            # Паттерн: code=module.path.to.function или code=module.path.0009_module.function
            problematic_pattern = re.compile(
                r'code=([a-z_][a-z0-9_.]*\.\d+[a-z0-9_]*\.[a-z_][a-z0-9_]*)',
                re.IGNORECASE
            )
            
            matches = problematic_pattern.findall(content)
            if not matches:
                return
            
            self.stdout.write('\nОбнаружены функции, требующие ручного копирования...')
            
            # Собираем все функции, которые нужно скопировать
            functions_to_copy = {}
            
            for match in matches:
                # Разбираем путь: app.migrations.0009_module.function_name
                parts = match.split('.')
                if len(parts) < 3:
                    continue
                
                # Находим номер миграции (часть, начинающаяся с цифры)
                migration_name = None
                function_name = None
                
                for i, part in enumerate(parts):
                    if part and part[0].isdigit():
                        migration_name = part
                        if i + 1 < len(parts):
                            function_name = parts[i + 1]
                        break
                
                if not migration_name or not function_name:
                    continue
                
                # Ищем исходную миграцию
                try:
                    original_migration = loader.get_migration(app_label, migration_name)
                except:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Не удалось найти миграцию {migration_name} для функции {function_name}'
                        )
                    )
                    continue
                
                # Ищем RunPython операции в оригинальной миграции
                for operation in original_migration.operations:
                    if hasattr(operation, 'code') and callable(operation.code):
                        # Получаем имя функции
                        op_func_name = getattr(operation.code, '__name__', None)
                        if op_func_name == function_name:
                            # Копируем функцию
                            try:
                                func_source = inspect.getsource(operation.code)
                                functions_to_copy[function_name] = {
                                    'source': func_source,
                                    'original_path': match
                                }
                                self.stdout.write(
                                    f'Найдена функция: {function_name} из {migration_name}'
                                )
                            except Exception as e:
                                self.stdout.write(
                                    self.style.WARNING(
                                        f'Не удалось получить исходный код функции {function_name}: {e}'
                                    )
                                )
            
            if not functions_to_copy:
                self.stdout.write(
                    self.style.WARNING('Функции не найдены или не могут быть скопированы автоматически.')
                )
                return
            
            # Вставляем функции в начало файла (после импортов)
            functions_code = '\n\n'.join([
                func_info['source'] 
                for func_info in functions_to_copy.values()
            ])
            
            # Находим место для вставки (после комментария о manual porting, перед классом Migration)
            class_pattern = re.compile(r'^(class Migration\(migrations\.Migration\):)', re.MULTILINE)
            match = class_pattern.search(content)
            
            if match:
                insert_pos = match.start()
                # Вставляем функции перед классом Migration
                content = (
                    content[:insert_pos] +
                    '\n' + functions_code + '\n\n' +
                    content[insert_pos:]
                )
                
                # Обновляем ссылки в RunPython операциях
                for func_name, func_info in functions_to_copy.items():
                    # Заменяем полный путь на просто имя функции
                    old_ref = f"code={func_info['original_path']}"
                    new_ref = f"code={func_name}"
                    content = content.replace(old_ref, new_ref)
                
                # Удаляем комментарий о manual porting, так как мы его исправили
                content = re.sub(
                    r'# Functions from the following migrations need manual copying\.\n'
                    r'# Move them and any dependencies into this file, then update the\n'
                    r'# RunPython operations to refer to the local versions:\n'
                    r'# [^\n]+\n\n',
                    '',
                    content
                )
                
                # Записываем обновленный файл
                with open(squash_file, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nАвтоматически скопировано функций: {len(functions_to_copy)}'
                    )
                )
                for func_name in functions_to_copy.keys():
                    self.stdout.write(f' - {func_name}')
            else:
                self.stdout.write(
                    self.style.WARNING('Не удалось найти место для вставки функций.')
                )
                
        except Exception as e:
            self.stdout.write(
                self.style.WARNING(
                    f'Ошибка при автоматическом исправлении функций: {e}\n'
                    'Проверьте squash миграцию вручную.'
                )
            )

