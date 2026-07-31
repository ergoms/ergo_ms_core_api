"""Вспомогательные функции для команды sq_del_migrations."""
import inspect
import re
from pathlib import Path

from django.apps import apps
from django.db import connection


def collect_statistics(stdout, app_label, migrations_to_squash, loader, migrations_dir):
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

    for migration_name in migrations_to_squash:
        migration_file = migrations_dir / f'{migration_name}.py'
        if migration_file.exists():
            stats['migration_files'].append(migration_name)
    stats['migration_files_count'] = len(stats['migration_files'])

    with connection.cursor() as cursor:
        placeholders = ','.join(['%s'] * len(migrations_to_squash))
        cursor.execute(
            f"SELECT name FROM django_migrations WHERE app = %s AND name IN ({placeholders})",
            [app_label] + migrations_to_squash
        )
        stats['db_records'] = [row[0] for row in cursor.fetchall()]
    stats['db_records_count'] = len(stats['db_records'])

    try:
        with connection.cursor() as cursor:
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
        stdout.write(
            stdout.style.WARNING(f'Не удалось получить список таблиц: {e}')
        )

    stats['tables_count'] = len(stats['tables'])

    return stats


def update_dependencies_in_other_apps(stdout, app_label, replaced_migrations, squash_migration_name, loader):
    """
    Автоматически обновляет зависимости в других приложениях,
    заменяя ссылки на замененные миграции на новую squash миграцию.
    """
    stdout.write('\nОбновление зависимостей в других приложениях...')

    updated_count = 0

    for (other_app, other_migration_name), other_migration in loader.graph.nodes.items():
        if other_app == app_label:
            continue

        needs_update = False
        new_dependencies = []

        for dep_app, dep_name in other_migration.dependencies:
            if dep_app == app_label and dep_name in replaced_migrations:
                new_dependencies.append((app_label, squash_migration_name))
                needs_update = True
                stdout.write(
                    f'Найдена зависимость: {other_app}.{other_migration_name} -> {app_label}.{dep_name}'
                )
            else:
                new_dependencies.append((dep_app, dep_name))

        if needs_update:
            try:
                other_app_config = apps.get_app_config(other_app)
                other_migrations_dir = Path(other_app_config.path) / 'migrations'
                other_migration_file = other_migrations_dir / f'{other_migration_name}.py'

                if not other_migration_file.exists():
                    stdout.write(
                        stdout.style.WARNING(
                            f'Файл миграции не найден: {other_migration_file}'
                        )
                    )
                    continue

                with open(other_migration_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                original_content = content
                for replaced_migration in replaced_migrations:
                    pattern = rf"\(\s*['\"]{re.escape(app_label)}['\"]\s*,\s*['\"]{re.escape(replaced_migration)}['\"]\s*\)"
                    replacement = f"('{app_label}', '{squash_migration_name}')"
                    content = re.sub(pattern, replacement, content)

                if content != original_content:
                    with open(other_migration_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    updated_count += 1
                    stdout.write(
                        stdout.style.SUCCESS(
                            f'Обновлена зависимость в {other_app}.{other_migration_name}'
                        )
                    )
                else:
                    stdout.write(
                        stdout.style.WARNING(
                            f'Не удалось найти зависимость в файле {other_migration_file}'
                        )
                    )

            except Exception as e:
                stdout.write(
                    stdout.style.WARNING(
                        f'Ошибка при обновлении {other_app}.{other_migration_name}: {e}'
                    )
                )

    if updated_count > 0:
        stdout.write(
            stdout.style.SUCCESS(
                f'\nОбновлено зависимостей в других приложениях: {updated_count}'
            )
        )
    else:
        stdout.write(
            stdout.style.SUCCESS(
                '\nЗависимости в других приложениях не требуют обновления'
            )
        )


def fix_runpython_functions(stdout, squash_file, migrations_to_squash, app_label, loader):
    """
    Автоматически копирует функции из RunPython операций в squash миграцию,
    если они находятся в модулях с именами, начинающимися с цифр.
    """
    try:
        with open(squash_file, 'r', encoding='utf-8') as f:
            content = f.read()

        if '# Functions from the following migrations need manual copying' not in content:
            return

        problematic_pattern = re.compile(
            r'code=([a-z_][a-z0-9_.]*\.\d+[a-z0-9_]*\.[a-z_][a-z0-9_]*)',
            re.IGNORECASE
        )

        matches = problematic_pattern.findall(content)
        if not matches:
            return

        stdout.write('\nОбнаружены функции, требующие ручного копирования...')

        functions_to_copy = {}

        for match in matches:
            parts = match.split('.')
            if len(parts) < 3:
                continue

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

            try:
                original_migration = loader.get_migration(app_label, migration_name)
            except Exception:
                stdout.write(
                    stdout.style.WARNING(
                        f'Не удалось найти миграцию {migration_name} для функции {function_name}'
                    )
                )
                continue

            for operation in original_migration.operations:
                if hasattr(operation, 'code') and callable(operation.code):
                    op_func_name = getattr(operation.code, '__name__', None)
                    if op_func_name == function_name:
                        try:
                            func_source = inspect.getsource(operation.code)
                            functions_to_copy[function_name] = {
                                'source': func_source,
                                'original_path': match
                            }
                            stdout.write(
                                f'Найдена функция: {function_name} из {migration_name}'
                            )
                        except Exception as e:
                            stdout.write(
                                stdout.style.WARNING(
                                    f'Не удалось получить исходный код функции {function_name}: {e}'
                                )
                            )

        if not functions_to_copy:
            stdout.write(
                stdout.style.WARNING('Функции не найдены или не могут быть скопированы автоматически.')
            )
            return

        functions_code = '\n\n'.join([
            func_info['source']
            for func_info in functions_to_copy.values()
        ])

        class_pattern = re.compile(r'^(class Migration\(migrations\.Migration\):)', re.MULTILINE)
        class_match = class_pattern.search(content)

        if class_match:
            insert_pos = class_match.start()
            content = (
                content[:insert_pos] +
                '\n' + functions_code + '\n\n' +
                content[insert_pos:]
            )

            for func_name, func_info in functions_to_copy.items():
                old_ref = f"code={func_info['original_path']}"
                new_ref = f"code={func_name}"
                content = content.replace(old_ref, new_ref)

            content = re.sub(
                r'# Functions from the following migrations need manual copying\.\n'
                r'# Move them and any dependencies into this file, then update the\n'
                r'# RunPython operations to refer to the local versions:\n'
                r'# [^\n]+\n\n',
                '',
                content
            )

            with open(squash_file, 'w', encoding='utf-8') as f:
                f.write(content)

            stdout.write(
                stdout.style.SUCCESS(
                    f'\nАвтоматически скопировано функций: {len(functions_to_copy)}'
                )
            )
            for func_name in functions_to_copy.keys():
                stdout.write(f' - {func_name}')
        else:
            stdout.write(
                stdout.style.WARNING('Не удалось найти место для вставки функций.')
            )

    except Exception as e:
        stdout.write(
            stdout.style.WARNING(
                f'Ошибка при автоматическом исправлении функций: {e}\n'
                'Проверьте squash миграцию вручную.'
            )
        )
