"""
Файл для определения команды Django для запуска development сервера.

Этот файл содержит класс Command, который наследуется от RunserverCommand и предоставляет 
функциональность для запуска сервера разработки с настройками хоста и порта из конфигурации.

Пример использования:
>>> ergoms api runserver [host:port]
"""

import logging
import os
import subprocess
import sys

try:
    from daphne.management.commands.runserver import Command as RunserverCommand
except ImportError:
    from django.core.management.commands.runserver import Command as RunserverCommand
from django.core.management.base import CommandParser

from django.conf import settings

from src.config.deploy import build_daphne_command, get_api_bind_host, get_api_bind_port, is_production
from src.config.paths import API_DIR
from src.core.utils.startup_timing import get_elapsed, get_elapsed_str

logger = logging.getLogger('core.utils.commands')


class _StreamTimingWrapper:
    """Обёртка stdout/stderr для вывода времени готовности API при появлении 'Starting'."""

    def __init__(self, stream):
        self._stream = stream
        self._ready_printed = False

    def _check_and_print_ready(self, data: str) -> None:
        if self._ready_printed:
            return
        if 'Starting' not in data or ('server' not in data.lower() and 'development' not in data.lower()):
            return
        elapsed = get_elapsed()
        suffix = 'ms' if elapsed < 1 else 's'
        val = elapsed * 1000 if elapsed < 1 else elapsed
        fmt = f'{val:.0f}{suffix}' if elapsed < 1 else f'{val:.2f}{suffix}'
        try:
            self._stream.write(f'\n>>> API готов (полное время запуска): {fmt}\n')
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass
        self._ready_printed = True

    def write(self, data: str) -> None:
        self._stream.write(data)
        self._check_and_print_ready(data)

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, name):
        return getattr(self._stream, name)


class Command(RunserverCommand):
    """
    Команда Django для запуска development сервера.
    
    Расширяет стандартную команду runserver для использования
    настроек хоста и порта из конфигурации проекта.
    """
    help = 'Запускает development сервер с необходимыми сервисами'

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Добавляет аргументы командной строки.

        Args:
            parser: Парсер аргументов командной строки
        """
        super().add_arguments(parser)

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду запуска сервера.

        Если адрес и порт не указаны явно, использует значения из настроек.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        if is_production():
            host = get_api_bind_host()
            port = get_api_bind_port()
            msg = f'API (запуск как на сервере): daphne на {host}:{port} (без autoreload)'
            logger.info(msg)
            try:
                self.stdout.write(self.style.SUCCESS(msg))
            except (UnicodeEncodeError, UnicodeDecodeError):
                pass
            cmd = build_daphne_command(sys.executable)
            raise SystemExit(subprocess.call(cmd, cwd=str(API_DIR)))

        is_reloader_child = os.environ.get('RUN_MAIN') == 'true'
        role = 'autoreload child (рабочий процесс)' if is_reloader_child else 'autoreload parent (launcher)'
        logger.info('Запуск команды runserver (%s)', role)
        if is_reloader_child:
            elapsed_msg = get_elapsed_str()
            try:
                self.stdout.write(self.style.SUCCESS(f'  API (runserver): Django загружен полностью {elapsed_msg}'))
            except (UnicodeEncodeError, UnicodeDecodeError):
                logger.info('API (runserver): Django загружен полностью %s', elapsed_msg)

        if not options['addrport']:
            server_host = getattr(settings, 'SERVER_HOST', None)
            server_port = getattr(settings, 'SERVER_PORT', None)

            if not all([server_host, server_port]):
                msg = 'SERVER_HOST или SERVER_PORT не настроены в конфигурации'
                logger.error(msg)
                raise ValueError(msg)

            addrport = f'{server_host}:{server_port}'
            logger.info(f'Используются настройки по умолчанию: {addrport}')
            options['addrport'] = addrport
        else:
            logger.info(f'Используются пользовательские настройки: {options["addrport"]}')
        
        try:
            orig_stdout = self.stdout
            self.stdout = _StreamTimingWrapper(orig_stdout)
            try:
                super().handle(*args, **options)
            finally:
                self.stdout = orig_stdout
        except Exception as e:
            msg = f'Ошибка при запуске сервера: {str(e)}'
            logger.error(msg)
            raise