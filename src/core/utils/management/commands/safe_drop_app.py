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


class Command(BaseCommand):
    help = (
        'Безопасно удаляет приложение Django: таблицы, данные, миграции. '
        'Проверяет зависимости других приложений перед удалением.'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            'app_label',
            type=str,
            help='Название приложения (например, settings)'
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
            help='Принудительно удалить даже при наличии зависимостей (опасно!)',
        )
        parser.add_argument(
            '--check-only',
            action='store_true',
            help='Только проверить зависимости, не выполнять удаление',
        )
        parser.add_argument(
            '--keep-migrations',
            action='store_true',
            help='Не удалять файлы миграций (только таблицы и данные)',
        )
        parser.add_argument(
            '--cascade',
            action='store_true',
            help='Удалить зависимые записи каскадно (через CASCADE)',
        )
        parser.add_argument(
            '--auto-fix',
            action='store_true',
            help='Автоматически удалить ссылающиеся поля из других моделей и создать миграции',
        )

    def handle(self, *args, **options):
        app_label = options['app_label']
        interactive = options.get('interactive', True)
        force = options.get('force', False)
        check_only = options.get('check_only', False)
        keep_migrations = options.get('keep_migrations', False)
        cascade = options.get('cascade', False)
        auto_fix = options.get('auto_fix', False)

        # Проверяем существование приложения
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            raise CommandError(f'Приложение "{app_label}" не найдено.')

        app_path = Path(app_config.path)
        migrations_dir = app_path / 'migrations'

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\nАнализ приложения: {app_label}'
        ))
        self.stdout.write('=' * 60)

        # 1. Собираем информацию о моделях и таблицах
        models_info = self._get_models_info(app_label)
        
        # 2. Проверяем зависимости других приложений (FK, M2M)
        model_dependencies = self._check_model_dependencies(app_label, models_info)
        
        # 3. Проверяем зависимости миграций
        migration_dependencies = self._check_migration_dependencies(app_label)
        
        # 4. Собираем статистику
        stats = self._collect_statistics(
            app_label, models_info, migrations_dir
        )

        # Выводим информацию о моделях
        self._print_models_info(models_info, stats)
        
        # Выводим зависимости моделей
        self._print_model_dependencies(model_dependencies)
        
        # Выводим зависимости миграций
        self._print_migration_dependencies(migration_dependencies)

        # Проверяем, есть ли блокирующие зависимости моделей (не миграций)
        has_model_deps = (
            model_dependencies['foreign_keys'] or 
            model_dependencies['many_to_many'] or
            model_dependencies['one_to_one']
        )

        # Фильтруем только исправляемые зависимости (не системные)
        fixable_model_deps = {
            'foreign_keys': [d for d in model_dependencies['foreign_keys'] if not d.get('is_system')],
            'many_to_many': [d for d in model_dependencies['many_to_many'] if not d.get('is_system')],
            'one_to_one': [d for d in model_dependencies['one_to_one'] if not d.get('is_system')],
        }
        has_fixable_deps = (
            fixable_model_deps['foreign_keys'] or 
            fixable_model_deps['many_to_many'] or 
            fixable_model_deps['one_to_one']
        )

        # Если есть зависимости и включен auto-fix
        if (has_fixable_deps or migration_dependencies) and auto_fix and not check_only:
            self.stdout.write(self.style.WARNING(
                '\n🔧 Автоматическое исправление зависимостей...'
            ))
            
            if interactive:
                if has_fixable_deps:
                    self.stdout.write(
                        '\nБудут удалены следующие поля из других приложений:'
                    )
                    for dep in fixable_model_deps['foreign_keys']:
                        self.stdout.write(f'  - {dep["app"]}.{dep["model"]}.{dep["field"]}')
                    for dep in fixable_model_deps['many_to_many']:
                        self.stdout.write(f'  - {dep["app"]}.{dep["model"]}.{dep["field"]}')
                    for dep in fixable_model_deps['one_to_one']:
                        self.stdout.write(f'  - {dep["app"]}.{dep["model"]}.{dep["field"]}')
                
                if migration_dependencies:
                    self.stdout.write(
                        '\nБудут исправлены зависимости миграций:'
                    )
                    for dep in migration_dependencies:
                        self.stdout.write(f'  - {dep["app"]}.{dep["migration"]}')
                
                response = input('\nВыполнить исправления? (yes/no): ')
                if response.lower() not in ('yes', 'y'):
                    self.stdout.write(self.style.ERROR('Отменено пользователем.'))
                    return
            
            # 1. Сначала исправляем зависимости миграций
            if migration_dependencies:
                self._fix_migration_dependencies(app_label, migration_dependencies)
            
            # 2. Удаляем поля из моделей
            fixed_apps = set()
            if has_fixable_deps:
                fixed_apps = self._auto_fix_dependencies(app_label, fixable_model_deps)
            
            # ВАЖНО: НЕ создаём миграции сейчас, т.к. Django кешировал старые модели
            # Миграции нужно создать ПОСЛЕ удаления приложения в отдельном процессе
            self._fixed_apps_for_migrations = fixed_apps if fixed_apps else set()
            
            if fixed_apps:
                self.stdout.write(self.style.WARNING(
                    '\n⚠️ Миграции будут созданы ПОСЛЕ удаления приложения.'
                ))
                self.stdout.write(
                    '   Django кеширует модели в памяти, поэтому миграции\n'
                    '   нужно создать в отдельном процессе после удаления.\n'
                )
            
            # Помечаем что auto-fix был выполнен — можем продолжать с --cascade
            # даже если Django ещё видит "призраки" старых моделей
            has_model_deps = False
            migration_dependencies = []

        # Проверяем, есть ли блокирующие зависимости
        has_blocking_deps = has_model_deps or migration_dependencies

        if has_blocking_deps and not force:
            self.stdout.write(self.style.ERROR(
                '\n❌ Обнаружены зависимости, которые блокируют удаление!'
            ))
            self.stdout.write(
                '\nВарианты решения:\n'
                '  1. Удалите зависимости вручную (ForeignKey, ManyToMany)\n'
                '  2. Используйте --cascade для каскадного удаления данных\n'
                '  3. Используйте --force для принудительного удаления (опасно!)\n'
                '  4. Используйте --auto-fix для автоматического удаления ссылок\n'
            )
            if check_only:
                return
            return

        if check_only:
            self.stdout.write(self.style.SUCCESS(
                '\n✓ Проверка завершена. Используйте без --check-only для удаления.'
            ))
            return

        # Подтверждение
        if interactive:
            self.stdout.write(self.style.WARNING(
                '\n⚠️  ВНИМАНИЕ: Эта операция необратима!'
            ))
            self.stdout.write(
                f'\nБудут удалены:\n'
                f'  - Таблицы: {stats["tables_count"]}\n'
                f'  - Записи в таблицах: ~{stats["total_records"]}\n'
                f'  - Записи в django_migrations: {stats["migration_records_count"]}\n'
            )
            if not keep_migrations:
                self.stdout.write(f'  - Файлы миграций: {stats["migration_files_count"]}')
            
            if cascade and model_dependencies['foreign_keys']:
                self.stdout.write(self.style.WARNING(
                    '\n⚠️  Также будут удалены зависимые записи из других таблиц!'
                ))
            
            response = input('\nПродолжить? (yes/no): ')
            if response.lower() not in ('yes', 'y'):
                self.stdout.write(self.style.ERROR('Отменено пользователем.'))
                return

        # Выполняем удаление
        self._perform_deletion(
            app_label, 
            models_info, 
            migrations_dir,
            keep_migrations,
            cascade,
            migration_dependencies
        )

        self.stdout.write(self.style.SUCCESS(
            f'\n✓ Приложение "{app_label}" успешно удалено!'
        ))
        
        # Проверяем, нужно ли создать миграции для исправленных приложений
        fixed_apps = getattr(self, '_fixed_apps_for_migrations', set())
        
        if fixed_apps:
            apps_list = ', '.join(fixed_apps)
            self.stdout.write(self.style.WARNING(
                f'\n⚠️ ВАЖНО: Необходимо создать и применить миграции!'
            ))
            self.stdout.write(
                f'\nВыполните следующие команды:\n'
                f'  ergoms api makemigrations {apps_list}\n'
                f'  ergoms api migrate\n'
            )
        
        self.stdout.write(
            '\nСледующие шаги:\n'
            '1. Удалите приложение из INSTALLED_APPS (если применимо)\n'
            '2. Удалите директорию приложения вручную (если нужно)\n'
            '3. Перезапустите Django сервер\n'
        )

    def _get_models_info(self, app_label):
        """Получает информацию о моделях приложения, включая M2M таблицы."""
        models_info = []
        m2m_tables = []  # Отдельно храним M2M таблицы
        
        try:
            app_config = apps.get_app_config(app_label)
            for model in app_config.get_models():
                table_name = model._meta.db_table
                
                # Получаем количество записей
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"SELECT COUNT(*) FROM {connection.ops.quote_name(table_name)}"
                        )
                        count = cursor.fetchone()[0]
                except Exception:
                    count = 0
                
                models_info.append({
                    'model': model,
                    'name': model.__name__,
                    'table': table_name,
                    'records': count,
                    'is_m2m': False,
                    'fields': {
                        f.name: f for f in model._meta.get_fields()
                    }
                })
                
                # Ищем ManyToMany поля и их промежуточные таблицы
                for field in model._meta.get_fields():
                    if field.many_to_many and hasattr(field, 'remote_field'):
                        # Проверяем, что это наше поле (не обратное отношение)
                        if hasattr(field, 'm2m_db_table'):
                            m2m_table = field.m2m_db_table()
                            
                            # Проверяем, что таблица принадлежит нашему приложению
                            if m2m_table.startswith(f'{app_label}_'):
                                # Получаем количество записей в M2M таблице
                                m2m_count = 0
                                try:
                                    with connection.cursor() as cursor:
                                        cursor.execute(
                                            f"SELECT COUNT(*) FROM {connection.ops.quote_name(m2m_table)}"
                                        )
                                        m2m_count = cursor.fetchone()[0]
                                except Exception:
                                    pass
                                
                                # Добавляем только если ещё не добавлена
                                if not any(t['table'] == m2m_table for t in m2m_tables):
                                    m2m_tables.append({
                                        'model': None,
                                        'name': f'{model.__name__}.{field.name} (M2M)',
                                        'table': m2m_table,
                                        'records': m2m_count,
                                        'is_m2m': True,
                                        'fields': {},
                                        'source_model': model.__name__,
                                        'field_name': field.name,
                                    })
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Ошибка при получении моделей: {e}'))
        
        # Добавляем M2M таблицы в общий список
        models_info.extend(m2m_tables)
        
        return models_info

    def _check_model_dependencies(self, app_label, models_info):
        """Проверяет зависимости других приложений на модели.
        
        Фильтрует:
        - Обратные связи (reverse relations) — они не являются реальными FK
        - Встроенные Django приложения (auth, contenttypes) — их нельзя изменять
        """
        from django.db.models.fields.related import ForeignObject, ManyToManyField
        
        dependencies = {
            'foreign_keys': [],
            'many_to_many': [],
            'one_to_one': [],
        }
        
        # Приложения, которые нельзя изменять
        SYSTEM_APPS = {'auth', 'contenttypes', 'sessions', 'admin', 'messages'}
        
        our_tables = {m['table'] for m in models_info}
        our_models = {m['model'] for m in models_info if m.get('model')}
        
        # Проходим по всем приложениям
        for app_config in apps.get_app_configs():
            if app_config.label == app_label:
                continue
            
            # Помечаем системные приложения
            is_system_app = app_config.label in SYSTEM_APPS
            
            for model in app_config.get_models():
                for field in model._meta.get_fields():
                    # Пропускаем обратные связи (reverse relations)
                    # Реальные поля имеют атрибут 'column' или являются ManyToManyField
                    is_real_field = (
                        hasattr(field, 'column') or 
                        isinstance(field, ManyToManyField)
                    )
                    if not is_real_field:
                        continue
                    
                    # Проверяем, что поле ссылается на наши модели
                    if not hasattr(field, 'related_model'):
                        continue
                    if field.related_model not in our_models:
                        continue
                    
                    # Получаем on_delete для FK
                    on_delete_name = 'unknown'
                    if hasattr(field, 'remote_field') and field.remote_field:
                        on_delete = getattr(field.remote_field, 'on_delete', None)
                        on_delete_name = on_delete.__name__ if on_delete else 'unknown'
                    
                    # Получаем количество связанных записей
                    related_count = 0
                    try:
                        with connection.cursor() as cursor:
                            table = model._meta.db_table
                            if isinstance(field, ManyToManyField):
                                # Для M2M считаем записи в промежуточной таблице
                                m2m_table = field.m2m_db_table()
                                cursor.execute(
                                    f"SELECT COUNT(*) FROM {connection.ops.quote_name(m2m_table)}"
                                )
                            else:
                                column = field.column if hasattr(field, 'column') else f'{field.name}_id'
                                cursor.execute(
                                    f"SELECT COUNT(*) FROM {connection.ops.quote_name(table)} "
                                    f"WHERE {connection.ops.quote_name(column)} IS NOT NULL"
                                )
                            related_count = cursor.fetchone()[0]
                    except Exception:
                        pass
                    
                    dep_info = {
                        'app': app_config.label,
                        'model': model.__name__,
                        'table': model._meta.db_table,
                        'field': field.name,
                        'related_to': field.related_model.__name__,
                        'on_delete': on_delete_name,
                        'related_count': related_count,
                        'is_system': is_system_app,  # Пометка системного приложения
                    }
                    
                    if hasattr(field, 'one_to_one') and field.one_to_one:
                        dependencies['one_to_one'].append(dep_info)
                    elif isinstance(field, ManyToManyField):
                        dependencies['many_to_many'].append(dep_info)
                    else:
                                dependencies['foreign_keys'].append(dep_info)
        
        return dependencies

    def _check_migration_dependencies(self, app_label):
        """Проверяет зависимости миграций других приложений."""
        dependencies = []
        
        loader = MigrationLoader(connection)
        
        # Получаем все миграции нашего приложения
        our_migrations = set()
        for (app, name) in loader.graph.nodes.keys():
            if app == app_label:
                our_migrations.add(name)
        
        # Проверяем зависимости других приложений
        for (app, name), migration in loader.graph.nodes.items():
            if app == app_label:
                continue
            
            for dep_app, dep_name in migration.dependencies:
                if dep_app == app_label and dep_name in our_migrations:
                    dependencies.append({
                        'app': app,
                        'migration': name,
                        'depends_on': dep_name,
                    })
        
        return dependencies

    def _collect_statistics(self, app_label, models_info, migrations_dir):
        """Собирает статистику для отображения."""
        stats = {
            'tables': [m['table'] for m in models_info],
            'tables_count': len(models_info),
            'total_records': sum(m['records'] for m in models_info),
            'migration_files': [],
            'migration_files_count': 0,
            'migration_records': [],
            'migration_records_count': 0,
        }
        
        # Файлы миграций
        if migrations_dir.exists():
            stats['migration_files'] = [
                f.stem for f in migrations_dir.glob('*.py')
                if f.name != '__init__.py' and not f.name.startswith('.')
            ]
            stats['migration_files_count'] = len(stats['migration_files'])
        
        # Записи в django_migrations
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT name FROM django_migrations WHERE app = %s ORDER BY name",
                    [app_label]
                )
                stats['migration_records'] = [row[0] for row in cursor.fetchall()]
                stats['migration_records_count'] = len(stats['migration_records'])
        except Exception:
            pass
        
        return stats

    def _print_models_info(self, models_info, stats):
        """Выводит информацию о моделях."""
        # Разделяем на обычные модели и M2M таблицы
        regular_models = [m for m in models_info if not m.get('is_m2m')]
        m2m_tables = [m for m in models_info if m.get('is_m2m')]
        
        self.stdout.write(f'\n📊 Модели и таблицы ({len(regular_models)}):')
        for model_info in regular_models:
            self.stdout.write(
                f'  - {model_info["name"]} -> {model_info["table"]} '
                f'({model_info["records"]} записей)'
            )
        
        if m2m_tables:
            self.stdout.write(f'\n🔗 ManyToMany таблицы ({len(m2m_tables)}):')
            for m2m in m2m_tables:
                self.stdout.write(
                    f'  - {m2m["name"]} -> {m2m["table"]} '
                    f'({m2m["records"]} связей)'
                )
        
        self.stdout.write(f'\n📁 Файлы миграций: {stats["migration_files_count"]}')
        self.stdout.write(f'📝 Записи в django_migrations: {stats["migration_records_count"]}')

    def _print_model_dependencies(self, dependencies):
        """Выводит зависимости моделей."""
        # Считаем только не-системные зависимости для основного счётчика
        fixable_deps = []
        system_deps = []
        
        for dep_type in ['foreign_keys', 'many_to_many', 'one_to_one']:
            for dep in dependencies[dep_type]:
                if dep.get('is_system'):
                    system_deps.append((dep_type, dep))
                else:
                    fixable_deps.append((dep_type, dep))
        
        total = len(fixable_deps) + len(system_deps)
        
        if not total:
            self.stdout.write(self.style.SUCCESS(
                '\n✓ Зависимости моделей из других приложений не найдены'
            ))
            return
        
        if fixable_deps:
            self.stdout.write(self.style.WARNING(
                f'\n⚠️  Зависимости моделей (исправляемые через --auto-fix): {len(fixable_deps)}'
            ))
            
            fk_deps = [d for t, d in fixable_deps if t == 'foreign_keys']
            m2m_deps = [d for t, d in fixable_deps if t == 'many_to_many']
            o2o_deps = [d for t, d in fixable_deps if t == 'one_to_one']
            
            if fk_deps:
                self.stdout.write('\n  ForeignKey:')
                for dep in fk_deps:
                    self.stdout.write(
                        f'    - {dep["app"]}.{dep["model"]}.{dep["field"]} -> '
                        f'{dep["related_to"]} (on_delete={dep["on_delete"]}, '
                        f'{dep["related_count"]} записей)'
                    )
            
            if m2m_deps:
                self.stdout.write('\n  ManyToMany:')
                for dep in m2m_deps:
                    self.stdout.write(
                        f'    - {dep["app"]}.{dep["model"]}.{dep["field"]} -> '
                        f'{dep["related_to"]} ({dep["related_count"]} связей)'
                    )
            
            if o2o_deps:
                self.stdout.write('\n  OneToOne:')
                for dep in o2o_deps:
                    self.stdout.write(
                        f'    - {dep["app"]}.{dep["model"]}.{dep["field"]} -> '
                        f'{dep["related_to"]} ({dep["related_count"]} записей)'
                    )
        
        if system_deps:
            self.stdout.write(self.style.NOTICE(
                f'\n📌 Системные зависимости (удалятся каскадно): {len(system_deps)}'
            ))
            for dep_type, dep in system_deps:
                self.stdout.write(
                    f'    - {dep["app"]}.{dep["model"]}.{dep["field"]} -> '
                    f'{dep["related_to"]} (системное приложение)'
                )

    def _print_migration_dependencies(self, dependencies):
        """Выводит зависимости миграций."""
        if not dependencies:
            self.stdout.write(self.style.SUCCESS(
                '\n✓ Зависимости миграций из других приложений не найдены'
            ))
            return
        
        self.stdout.write(self.style.WARNING(
            f'\n⚠️  Найдено зависимостей миграций: {len(dependencies)}'
        ))
        
        for dep in dependencies:
            self.stdout.write(
                f'  • {dep["app"]}.{dep["migration"]} -> {dep["depends_on"]}'
            )

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
        self.stdout.write('\n🔧 Исправление зависимостей миграций...')
        
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
                        f'  ⚠️ Файл не найден: {migration_file}'
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
                        f'  ✓ Удалена зависимость из {dep["app"]}.{dep["migration"]}'
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠️ Зависимость не найдена в файле {dep["app"]}.{dep["migration"]}'
                    ))
                    
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️ Ошибка при исправлении {dep["app"]}.{dep["migration"]}: {e}'
                ))
        
        # ВАЖНО: Удаляем записи из django_migrations для исправленных миграций
        # Это необходимо, потому что Django кеширует зависимости и будет ругаться
        # на несуществующую зависимость settings.XXXX даже после изменения файла
        if migrations_to_reset:
            self.stdout.write('\n🗑️ Сброс записей миграций в django_migrations...')
            for app, migration in migrations_to_reset:
                try:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM django_migrations WHERE app = %s AND name = %s",
                            [app, migration]
                        )
                        if cursor.rowcount > 0:
                            self.stdout.write(self.style.SUCCESS(
                                f'  ✓ Удалена запись {app}.{migration}'
                            ))
                        else:
                            self.stdout.write(
                                f'  ℹ️ Запись {app}.{migration} не найдена в БД'
                            )
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠️ Ошибка при удалении записи {app}.{migration}: {e}'
                    ))
        
        # Также чистим ВСЕ миграции затронутых приложений от ссылок на удаляемое приложение
        # (не только dependencies, но и операции AddField, CreateModel и т.д.)
        affected_apps = set(dep['app'] for dep in dependencies)
        for affected_app in affected_apps:
            self._clean_all_migrations_from_app_refs(affected_app, app_label)
        
        if fixed > 0:
            self.stdout.write(self.style.SUCCESS(f'\n  Исправлено миграций: {fixed}'))
        
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
            
            self.stdout.write(f'\n🧹 Поиск миграций {affected_app} со ссылками на {removed_app}...')
            
            migrations_to_delete = []
            
            for migration_file in migrations_dir.glob('*.py'):
                if migration_file.name == '__init__.py':
                    continue
                
                try:
                    with open(migration_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Проверяем, есть ли ссылки на removed_app
                    has_refs = (
                        f"'{removed_app}." in content or 
                        f'"{removed_app}.' in content or
                        f"'{removed_app}'," in content or
                        f'"{removed_app}",' in content
                    )
                    
                    if has_refs:
                        migrations_to_delete.append(migration_file)
                        
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠️ Ошибка при проверке {migration_file.name}: {e}'
                    ))
            
            if not migrations_to_delete:
                self.stdout.write('  Миграции со ссылками не найдены')
                return
            
            self.stdout.write(f'\n🗑️ Удаление {len(migrations_to_delete)} миграций со ссылками на {removed_app}...')
            
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
                            self.stdout.write(f'  ✓ Удалена запись из БД: {migration_name}')
                except Exception:
                    pass
                
                # Удаляем файл
                try:
                    migration_file.unlink()
                    self.stdout.write(f'  ✓ Удалён файл: {migration_file.name}')
                except Exception as e:
                    self.stdout.write(self.style.WARNING(
                        f'  ⚠️ Ошибка при удалении {migration_file.name}: {e}'
                    ))
            
            self.stdout.write(self.style.SUCCESS(
                f'  Удалено миграций: {len(migrations_to_delete)}'
            ))
                
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'  ⚠️ Ошибка при очистке миграций {affected_app}: {e}'
            ))

    def _update_migration_dependencies(self, app_label, dependencies):
        """Обновляет зависимости в миграциях других приложений (при удалении)."""
        self.stdout.write('\n🔄 Обновление зависимостей миграций...')
        
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
                    self.stdout.write(f'  ✓ {dep["app"]}.{dep["migration"]}')
                    
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️ Ошибка при обновлении {dep["app"]}.{dep["migration"]}: {e}'
                ))
        
        self.stdout.write(f'  Обновлено миграций: {updated}')

    def _drop_tables(self, models_info, cascade):
        """Удаляет таблицы из БД."""
        self.stdout.write('\n🗑️ Удаление таблиц...')
        
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
                self.stdout.write(f'  ✓ {table}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️ Ошибка при удалении {table}: {e}'
                ))
        
        self.stdout.write(f'  Удалено таблиц: {dropped}')

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
        self.stdout.write('\n🗑️ Удаление записей из django_migrations...')
        
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM django_migrations WHERE app = %s",
                    [app_label]
                )
                deleted = cursor.rowcount
            self.stdout.write(f'  ✓ Удалено записей: {deleted}')
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'  ⚠️ Ошибка при удалении записей: {e}'
            ))

    def _delete_migration_files(self, migrations_dir):
        """Удаляет файлы миграций."""
        self.stdout.write('\n🗑️ Удаление файлов миграций...')
        
        deleted = 0
        for migration_file in migrations_dir.glob('*.py'):
            if migration_file.name == '__init__.py':
                continue
            try:
                migration_file.unlink()
                deleted += 1
                self.stdout.write(f'  ✓ {migration_file.name}')
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️ Ошибка при удалении {migration_file.name}: {e}'
                ))
        
        self.stdout.write(f'  Удалено файлов: {deleted}')

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
                    f'  ⚠️ Не удалось найти приложение {dep["app"]}: {e}'
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
                            f'  ✓ Удалено поле {dep["model"]}.{dep["field"]} '
                            f'из {models_file.name}'
                        ))
                        
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️ Ошибка при обработке {models_file}: {e}'
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
        
        self.stdout.write('\n📝 Создание миграций для изменённых приложений...')
        
        for app_label in app_labels:
            try:
                self.stdout.write(f'  Создание миграций для {app_label}...')
                call_command('makemigrations', app_label, verbosity=0)
                self.stdout.write(self.style.SUCCESS(f'  ✓ {app_label}'))
            except Exception as e:
                self.stdout.write(self.style.WARNING(
                    f'  ⚠️ Ошибка при создании миграций для {app_label}: {e}'
                ))

    def _apply_migrations(self):
        """Применяет все миграции."""
        from django.core.management import call_command
        
        self.stdout.write('\n📦 Применение миграций...')
        
        try:
            call_command('migrate', verbosity=0)
            self.stdout.write(self.style.SUCCESS('  ✓ Миграции применены'))
        except Exception as e:
            self.stdout.write(self.style.WARNING(
                f'  ⚠️ Ошибка при применении миграций: {e}'
            ))

