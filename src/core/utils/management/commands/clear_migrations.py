"""
Файл для определения команды Django для очистки миграций приложения.

Эта команда удаляет все файлы миграций приложения (кроме __init__.py) и
удаляет все таблицы приложения из базы данных, а также записи о миграциях
из таблицы django_migrations.

Пример использования:
>>> python src/manage.py clear_migrations settings
>>> python src/manage.py clear_migrations settings --noinput
>>> python src/manage.py clear_migrations settings --database=default
"""

import logging
import os
import shutil
from pathlib import Path

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.recorder import MigrationRecorder

logger = logging.getLogger('core.utils.commands')


class Command(BaseCommand):
    """
    Команда Django для очистки миграций приложения.
    
    Удаляет все файлы миграций приложения (кроме __init__.py) и
    удаляет все таблицы приложения из базы данных, а также записи
    о миграциях из таблицы django_migrations.
    """
    help = 'Очищает миграции приложения и удаляет его таблицы из БД'

    def add_arguments(self, parser):
        """
        Добавляет аргументы командной строки.

        Args:
            parser: Парсер аргументов командной строки
        """
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
            '--database',
            default=DEFAULT_DB_ALIAS,
            choices=tuple(connections),
            help=f'База данных для использования. По умолчанию: {DEFAULT_DB_ALIAS}',
        )

    def handle(self, *args, **options):
        """
        Выполняет команду очистки миграций.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        app_label = options['app_label']
        database = options['database']
        interactive = options['interactive']
        verbosity = options.get('verbosity', 1)

        logger.info(f'Запуск команды clear_migrations для приложения: {app_label}')

        # Проверяем, существует ли приложение
        try:
            app_config = apps.get_app_config(app_label)
        except LookupError:
            raise CommandError(f'Приложение "{app_label}" не найдено.')

        app_path = Path(app_config.path)
        migrations_dir = app_path / 'migrations'

        # Проверяем, существует ли директория migrations
        if not migrations_dir.exists():
            raise CommandError(
                f'Директория migrations не найдена для приложения "{app_label}" '
                f'по пути: {migrations_dir}'
            )

        # Получаем список файлов миграций
        migration_files = [
            f for f in migrations_dir.iterdir()
            if f.is_file() and f.name != '__init__.py' and not f.name.startswith('.')
        ]

        if not migration_files:
            self.stdout.write(
                self.style.WARNING(
                    f'Файлы миграций не найдены в приложении "{app_label}"'
                )
            )
            return

        # Подсчитываем таблицы приложения в БД
        connection = connections[database]
        app_models = app_config.get_models()
        table_names = []
        
        with connection.cursor() as cursor:
            existing_tables = connection.introspection.table_names(cursor)
            converter = connection.introspection.identifier_converter
            
            for model in app_models:
                table_name = converter(model._meta.db_table)
                if connection.features.ignores_table_name_case:
                    table_name = table_name.lower()
                    existing_tables = [t.lower() for t in existing_tables]
                
                if table_name in existing_tables:
                    table_names.append(model._meta.db_table)

        # Подсчитываем записи о миграциях в БД
        recorder = MigrationRecorder(connection)
        migration_records_count = 0
        
        if recorder.has_table():
            migration_records_count = recorder.migration_qs.filter(app=app_label).count()

        # Показываем информацию о том, что будет удалено
        if verbosity >= 1:
            self.stdout.write(
                self.style.WARNING(
                    f'\nБудет удалено:\n'
                    f'  - Файлов миграций: {len(migration_files)}\n'
                    f'  - Таблиц в БД: {len(table_names)}\n'
                    f'  - Записей о миграциях в django_migrations: {migration_records_count}\n'
                )
            )
            
            if migration_files and verbosity >= 2:
                self.stdout.write('Файлы миграций:')
                for f in sorted(migration_files):
                    self.stdout.write(f'  - {f.name}')
            
            if table_names and verbosity >= 2:
                self.stdout.write('Таблицы в БД:')
                for table in sorted(table_names):
                    self.stdout.write(f'  - {table}')

        # Запрашиваем подтверждение
        if interactive:
            confirm = input(
                f'\nВы уверены, что хотите удалить все миграции и таблицы '
                f'приложения "{app_label}" из базы данных "{database}"?\n'
                f'Это действие НЕОБРАТИМО!\n\n'
                f'Введите "yes" для подтверждения, или "no" для отмены: '
            )
        else:
            confirm = 'yes'

        if confirm.lower() != 'yes':
            self.stdout.write(self.style.WARNING('Операция отменена.'))
            return

        try:
            # Удаляем файлы миграций
            deleted_files = []
            for migration_file in migration_files:
                try:
                    migration_file.unlink()
                    deleted_files.append(migration_file.name)
                    if verbosity >= 2:
                        self.stdout.write(f'Удалён файл: {migration_file.name}')
                except Exception as e:
                    logger.error(f'Ошибка при удалении файла {migration_file.name}: {e}')
                    self.stdout.write(
                        self.style.ERROR(f'Ошибка при удалении файла {migration_file.name}: {e}')
                    )

            # Удаляем таблицы из БД
            deleted_tables = []
            if table_names:
                with connection.schema_editor() as schema_editor:
                    # Отключаем проверку ограничений для более быстрого удаления
                    connection.disable_constraint_checking()
                    
                    for model in app_models:
                        try:
                            table_name = model._meta.db_table
                            # Проверяем, существует ли таблица
                            with connection.cursor() as cursor:
                                existing_tables = connection.introspection.table_names(cursor)
                                converter = connection.introspection.identifier_converter
                                db_table_name = converter(table_name)
                                
                                if connection.features.ignores_table_name_case:
                                    db_table_name = db_table_name.lower()
                                    existing_tables = [t.lower() for t in existing_tables]
                                
                                if db_table_name in existing_tables:
                                    schema_editor.delete_model(model)
                                    deleted_tables.append(table_name)
                                    if verbosity >= 2:
                                        self.stdout.write(f'Удалена таблица: {table_name}')
                        except Exception as e:
                            logger.error(f'Ошибка при удалении таблицы {model._meta.db_table}: {e}')
                            self.stdout.write(
                                self.style.ERROR(
                                    f'Ошибка при удалении таблицы {model._meta.db_table}: {e}'
                                )
                            )
                    
                    # Включаем проверку ограничений обратно
                    connection.enable_constraint_checking()

            # Удаляем записи о миграциях из django_migrations
            deleted_migration_records = 0
            if recorder.has_table():
                try:
                    deleted_migration_records = recorder.migration_qs.filter(app=app_label).delete()[0]
                    if verbosity >= 2:
                        self.stdout.write(
                            f'Удалено записей о миграциях: {deleted_migration_records}'
                        )
                except Exception as e:
                    logger.error(f'Ошибка при удалении записей о миграциях: {e}')
                    self.stdout.write(
                        self.style.ERROR(f'Ошибка при удалении записей о миграциях: {e}')
                    )

            # Удаляем директорию __pycache__ если она существует
            pycache_dir = migrations_dir / '__pycache__'
            if pycache_dir.exists():
                try:
                    shutil.rmtree(pycache_dir)
                    if verbosity >= 2:
                        self.stdout.write('Удалена директория __pycache__')
                except Exception as e:
                    logger.warning(f'Не удалось удалить __pycache__: {e}')

            # Выводим итоговую информацию
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nОчистка миграций завершена успешно!\n'
                    f'  - Удалено файлов миграций: {len(deleted_files)}\n'
                    f'  - Удалено таблиц в БД: {len(deleted_tables)}\n'
                    f'  - Удалено записей о миграциях: {deleted_migration_records}'
                )
            )

            logger.info(
                f'Очистка миграций для приложения "{app_label}" завершена. '
                f'Удалено файлов: {len(deleted_files)}, таблиц: {len(deleted_tables)}, '
                f'записей о миграциях: {deleted_migration_records}'
            )

        except Exception as e:
            msg = f'Ошибка при очистке миграций: {str(e)}'
            logger.error(msg, exc_info=True)
            raise CommandError(msg)

