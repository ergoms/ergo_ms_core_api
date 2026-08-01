"""Вспомогательные функции для команды sq_del_migrations."""
import ast
import inspect
import re
from pathlib import Path

from django.apps import apps
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

MANUAL_COPY_MARKER = '# Functions from the following migrations need manual copying'


def _resolve_style(stdout, style=None):
    """Django style живёт на Command.style, не на stdout."""
    if style is not None:
        return style
    from django.core.management.color import no_style
    return no_style()


def list_migration_stems(migrations_dir):
    """Stem'ы *.py в каталоге migrations (без __init__)."""
    return {
        f.stem
        for f in migrations_dir.glob('*.py')
        if f.name != '__init__.py' and not f.name.startswith('.')
    }


def collect_statistics(
    stdout, app_label, migrations_to_squash, loader, migrations_dir, style=None
):
    """
    Собирает статистику о миграциях, applied-статусе и таблицах.
    Не подразумевает удаление записей django_migrations.
    """
    style = _resolve_style(stdout, style)
    stats = {
        'migration_files': [],
        'migration_files_count': 0,
        'applied_records': [],
        'applied_records_count': 0,
        'tables': [],
        'tables_count': 0,
    }

    for migration_name in migrations_to_squash:
        migration_file = migrations_dir / f'{migration_name}.py'
        if migration_file.exists():
            stats['migration_files'].append(migration_name)
    stats['migration_files_count'] = len(stats['migration_files'])

    if migrations_to_squash:
        with connection.cursor() as cursor:
            placeholders = ','.join(['%s'] * len(migrations_to_squash))
            cursor.execute(
                f'SELECT name FROM django_migrations '
                f'WHERE app = %s AND name IN ({placeholders})',
                [app_label] + list(migrations_to_squash),
            )
            stats['applied_records'] = [row[0] for row in cursor.fetchall()]
    stats['applied_records_count'] = len(stats['applied_records'])

    try:
        with connection.cursor() as cursor:
            table_prefix = f'{app_label}_'
            cursor.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_name LIKE %s
                ORDER BY table_name
                """,
                [f'{table_prefix}%'],
            )
            stats['tables'] = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        stdout.write(style.WARNING(f'Не удалось получить список таблиц: {e}'))

    stats['tables_count'] = len(stats['tables'])
    return stats


def read_replaces(squash_path):
    """
    Читает имена миграций из replaces = [...] в файле squash.
    Возвращает список stem'ов (без app_label).
    """
    content = Path(squash_path).read_text(encoding='utf-8')
    match = re.search(
        r'^(\s*)replaces\s*=\s*(\[[\s\S]*?\])',
        content,
        re.MULTILINE,
    )
    if not match:
        return []

    try:
        replaces_value = ast.literal_eval(match.group(2))
    except (SyntaxError, ValueError):
        return []

    names = []
    for item in replaces_value:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            names.append(item[1])
        elif isinstance(item, str):
            names.append(item)
    return names


def find_squash_migration_file(migrations_dir, before_stems=None, squash_name=None):
    """
    Находит файл squash-миграции.

    - squash_name: явный stem
    - before_stems: stem'ы до создания; новый файл с replaces
    - иначе единственный *.py с непустым replaces
    """
    migrations_dir = Path(migrations_dir)

    if squash_name:
        candidate = migrations_dir / f'{squash_name}.py'
        if not candidate.exists():
            raise CommandError(
                f'Squash миграция не найдена: {candidate.name}'
            )
        if not read_replaces(candidate):
            raise CommandError(
                f'В {candidate.name} нет атрибута replaces '
                f'(уже finalize или не squash).'
            )
        return candidate

    candidates = []
    for path in sorted(migrations_dir.glob('*.py')):
        if path.name == '__init__.py' or path.name.startswith('.'):
            continue
        replaces = read_replaces(path)
        if not replaces:
            continue
        if before_stems is not None and path.stem in before_stems:
            # create: интересует только новый файл, не старый squash
            continue
        candidates.append(path)

    if not candidates:
        raise CommandError(
            'Squash миграция не найдена. Укажите --squash-name '
            'или сначала выполните --phase create.'
        )
    if len(candidates) > 1:
        names = ', '.join(p.stem for p in candidates)
        raise CommandError(
            f'Найдено несколько squash миграций: {names}. '
            f'Укажите --squash-name.'
        )
    return candidates[0]


def strip_replaces(squash_path):
    """Удаляет блок replaces = [...] из файла squash-миграции."""
    path = Path(squash_path)
    content = path.read_text(encoding='utf-8')
    # Только пробелы/табы после ], затем ровно один перевод строки —
    # иначе \s* съедает отступ следующего атрибута (dependencies).
    new_content, count = re.subn(
        r'^[ \t]*replaces\s*=\s*\[[\s\S]*?\][ \t]*\r?\n',
        '',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    if count == 0:
        raise CommandError(
            f'Не удалось снять replaces в {path.name}'
        )
    path.write_text(new_content, encoding='utf-8')


def assert_squash_ready_for_finalize(app_label, squash_name, replaces, db_connection=None):
    """
    Проверяет, что squash можно finalize:
    запись squash в django_migrations ИЛИ все replaces уже applied.
    """
    conn = db_connection or connection
    recorder = MigrationRecorder(conn)
    applied = {
        name
        for app, name in recorder.applied_migrations()
        if app == app_label
    }

    if squash_name in applied:
        return

    replaces_set = set(replaces)
    if replaces_set and replaces_set.issubset(applied):
        return

    missing = sorted(replaces_set - applied) if replaces_set else []
    detail = (
        f'Не применены: {", ".join(missing[:10])}'
        + ('...' if len(missing) > 10 else '')
        if missing
        else f'нет записи {app_label}.{squash_name}'
    )
    raise CommandError(
        f'Squash ещё не готов к finalize ({detail}). '
        f'Сначала выполните: ergoms db-migrate'
    )


def collect_external_dependencies(loader, app_label, migration_names):
    """Внешние зависимости / run_before на перечисленные миграции app."""
    names = set(migration_names)
    found = []
    for (app_name, migration_name), migration in loader.graph.nodes.items():
        if app_name == app_label:
            continue
        for dep_app, dep_name in migration.dependencies:
            if dep_app == app_label and dep_name in names:
                found.append({
                    'app': app_name,
                    'migration': migration_name,
                    'depends_on': (app_label, dep_name),
                    'type': 'dependency',
                })
        for dep_app, dep_name in getattr(migration, 'run_before', []):
            if dep_app == app_label and dep_name in names:
                found.append({
                    'app': app_name,
                    'migration': migration_name,
                    'depends_on': (app_label, dep_name),
                    'type': 'run_before',
                })
    return found


def update_dependencies_in_other_apps(
    stdout, app_label, replaced_migrations, squash_migration_name, loader, style=None
):
    """
    Обновляет зависимости в других приложениях и в том же app
    (миграции после диапазона squash): ссылки на replaced → squash.
    """
    style = _resolve_style(stdout, style)
    stdout.write('\nОбновление зависимостей (другие apps и хвост того же app)...')
    replaced_set = set(replaced_migrations)
    updated_count = 0

    for (other_app, other_migration_name), other_migration in loader.graph.nodes.items():
        # Пропускаем сам squash и заменяемые миграции (их файлы будут удалены)
        if other_app == app_label and (
            other_migration_name == squash_migration_name
            or other_migration_name in replaced_set
        ):
            continue

        needs_update = any(
            dep_app == app_label and dep_name in replaced_set
            for dep_app, dep_name in other_migration.dependencies
        )
        if not needs_update:
            continue

        for dep_app, dep_name in other_migration.dependencies:
            if dep_app == app_label and dep_name in replaced_set:
                stdout.write(
                    f'Найдена зависимость: {other_app}.{other_migration_name} '
                    f'-> {app_label}.{dep_name}'
                )

        try:
            other_app_config = apps.get_app_config(other_app)
            other_migration_file = (
                Path(other_app_config.path) / 'migrations' / f'{other_migration_name}.py'
            )
            if not other_migration_file.exists():
                stdout.write(
                    style.WARNING(
                        f'Файл миграции не найден: {other_migration_file}'
                    )
                )
                continue

            content = other_migration_file.read_text(encoding='utf-8')
            original_content = content
            replacement = f"('{app_label}', '{squash_migration_name}')"

            for replaced_migration in replaced_migrations:
                pattern = (
                    rf"\(\s*['\"]{re.escape(app_label)}['\"]\s*,\s*"
                    rf"['\"]{re.escape(replaced_migration)}['\"]\s*\)"
                )
                content = re.sub(pattern, replacement, content)

            # Дедуп повторяющихся ссылок на squash в dependencies
            content = _dedupe_dependency_tuples(content, app_label, squash_migration_name)

            if content != original_content:
                other_migration_file.write_text(content, encoding='utf-8')
                updated_count += 1
                stdout.write(
                    style.SUCCESS(
                        f'Обновлена зависимость в {other_app}.{other_migration_name}'
                    )
                )
            else:
                stdout.write(
                    style.WARNING(
                        f'Не удалось найти зависимость в файле {other_migration_file}'
                    )
                )
        except Exception as e:
            stdout.write(
                style.WARNING(
                    f'Ошибка при обновлении {other_app}.{other_migration_name}: {e}'
                )
            )

    if updated_count > 0:
        stdout.write(
            style.SUCCESS(
                f'\nОбновлено зависимостей в других приложениях: {updated_count}'
            )
        )
    else:
        stdout.write(
            style.SUCCESS(
                '\nЗависимости в других приложениях не требуют обновления'
            )
        )


def _dedupe_dependency_tuples(content, app_label, squash_migration_name):
    """Убирает дубликаты ('app', 'squash') внутри одного списка dependencies."""
    tuple_re = re.compile(
        rf"\(\s*['\"]{re.escape(app_label)}['\"]\s*,\s*"
        rf"['\"]{re.escape(squash_migration_name)}['\"]\s*\)"
    )
    replacement = f"('{app_label}', '{squash_migration_name}')"

    def dedupe_block(match):
        block = match.group(0)
        count = len(tuple_re.findall(block))
        if count <= 1:
            return block
        cleaned = tuple_re.sub('__SQUASH_DEP__', block)
        cleaned = cleaned.replace('__SQUASH_DEP__', replacement, 1)
        cleaned = cleaned.replace('__SQUASH_DEP__', '')
        cleaned = re.sub(r',\s*,', ',', cleaned)
        cleaned = re.sub(r'\[\s*,', '[', cleaned)
        cleaned = re.sub(r',\s*\]', ']', cleaned)
        return cleaned

    return re.sub(
        r'dependencies\s*=\s*\[[\s\S]*?\]',
        dedupe_block,
        content,
        count=1,
    )


def _extract_runpython_callables(operation):
    """Пары (attr_name, callable) для code / reverse_code."""
    result = []
    for attr in ('code', 'reverse_code'):
        func = getattr(operation, attr, None)
        if callable(func) and not isinstance(func, type):
            # migrations.RunPython.noop — пропускаем
            if getattr(func, '__name__', '') == 'noop':
                continue
            result.append((attr, func))
    return result


def fix_runpython_functions(
    stdout, squash_file, migrations_to_squash, app_label, loader, style=None
):
    """
    Копирует функции RunPython (code и reverse_code) в squash-файл.
    Возвращает True, если файл готов (нет маркера manual copying).
    """
    style = _resolve_style(stdout, style)
    squash_path = Path(squash_file)
    try:
        content = squash_path.read_text(encoding='utf-8')

        if MANUAL_COPY_MARKER not in content:
            return True

        stdout.write('\nОбнаружены функции, требующие копирования в squash...')

        # code=module.path.func и reverse_code=...
        ref_pattern = re.compile(
            r'(?:code|reverse_code)=([a-z_][a-z0-9_.]*\.\d+[a-z0-9_]*\.[a-z_][a-z0-9_]*)',
            re.IGNORECASE,
        )
        matches = ref_pattern.findall(content)
        if not matches:
            stdout.write(
                style.WARNING(
                    'Маркер manual copying есть, но ссылки на функции не распознаны.'
                )
            )
            return False

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
            if function_name in functions_to_copy:
                continue

            try:
                original_migration = loader.get_migration(app_label, migration_name)
            except Exception:
                stdout.write(
                    style.WARNING(
                        f'Не удалось найти миграцию {migration_name} '
                        f'для функции {function_name}'
                    )
                )
                continue

            found = False
            for operation in original_migration.operations:
                for _attr, func in _extract_runpython_callables(operation):
                    if getattr(func, '__name__', None) != function_name:
                        continue
                    try:
                        func_source = inspect.getsource(func)
                        functions_to_copy[function_name] = {
                            'source': func_source,
                            'original_paths': [match],
                        }
                        stdout.write(
                            f'Найдена функция: {function_name} из {migration_name}'
                        )
                        found = True
                    except Exception as e:
                        stdout.write(
                            style.WARNING(
                                f'Не удалось получить исходный код '
                                f'функции {function_name}: {e}'
                            )
                        )
                    break
                if found:
                    break
            else:
                # накопить original_path если функция уже есть
                if function_name in functions_to_copy:
                    paths = functions_to_copy[function_name]['original_paths']
                    if match not in paths:
                        paths.append(match)

        # Дописать все original_paths из matches
        for match in matches:
            parts = match.split('.')
            function_name = None
            for i, part in enumerate(parts):
                if part and part[0].isdigit() and i + 1 < len(parts):
                    function_name = parts[i + 1]
                    break
            if function_name and function_name in functions_to_copy:
                paths = functions_to_copy[function_name]['original_paths']
                if match not in paths:
                    paths.append(match)

        if not functions_to_copy:
            stdout.write(
                style.WARNING(
                    'Функции не найдены или не могут быть скопированы автоматически.'
                )
            )
            return False

        functions_code = '\n\n'.join(
            func_info['source'] for func_info in functions_to_copy.values()
        )

        class_pattern = re.compile(
            r'^(class Migration\(migrations\.Migration\):)',
            re.MULTILINE,
        )
        class_match = class_pattern.search(content)
        if not class_match:
            stdout.write(
                style.WARNING('Не удалось найти место для вставки функций.')
            )
            return False

        insert_pos = class_match.start()
        content = (
            content[:insert_pos]
            + '\n'
            + functions_code
            + '\n\n'
            + content[insert_pos:]
        )

        for func_name, func_info in functions_to_copy.items():
            for original_path in func_info['original_paths']:
                content = content.replace(
                    f'code={original_path}',
                    f'code={func_name}',
                )
                content = content.replace(
                    f'reverse_code={original_path}',
                    f'reverse_code={func_name}',
                )

        content = re.sub(
            r'# Functions from the following migrations need manual copying\.\n'
            r'# Move them and any dependencies into this file, then update the\n'
            r'# RunPython operations to refer to the local versions:\n'
            r'(?:# [^\n]+\n)*\n?',
            '',
            content,
        )

        squash_path.write_text(content, encoding='utf-8')
        stdout.write(
            style.SUCCESS(
                f'\nАвтоматически скопировано функций: {len(functions_to_copy)}'
            )
        )
        for func_name in functions_to_copy:
            stdout.write(f' - {func_name}')

        return MANUAL_COPY_MARKER not in content

    except CommandError:
        raise
    except Exception as e:
        stdout.write(
            style.WARNING(
                f'Ошибка при автоматическом исправлении функций: {e}\n'
                'Проверьте squash миграцию вручную.'
            )
        )
        return False
