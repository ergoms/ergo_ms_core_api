"""
Файл для определения команды Django для запуска Daphne сервера.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для запуска Daphne сервера с настройкой уровня логирования.

Пример использования:
>>> python src/manage.py start_prod [--log-level=info]
"""

import logging

from django.core.management.base import BaseCommand, CommandParser

from src.core.utils.enums import LogLevel
from src.core.utils.server.daphne import Daphne

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для запуска production сервера.
    
    Запускает Daphne сервер с указанным уровнем логирования и проверяет
    успешность запуска процесса.
    """
    help = "Запуск production сервера (Daphne)"

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Добавляет аргументы командной строки.

        Args:
            parser: Парсер аргументов командной строки
        """
        parser.add_argument(
            '--log-level',
            type=str,
            choices=[level.value for level in LogLevel],
            default=LogLevel.INFO.value,
            help='Уровень логирования (info, warning, error, none)'
        )

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду запуска сервера.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы, включая log_level
        """
        logger.info('Запуск команды start_prod')
        
        log_level = LogLevel(options['log_level'])
        daphne = Daphne()
        
        logger.info(f'Запуск Daphne сервера с уровнем логирования: {log_level.value}')
        process = daphne.start_daphne(log_level)

        is_process_running = daphne.is_process_running(process)

        if is_process_running:
            msg = 'Сервер успешно запущен'
            logger.info(msg)
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            msg = 'Не удалось запустить сервер'
            logger.error(msg)
            self.stdout.write(self.style.ERROR(msg))