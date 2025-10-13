"""
Файл для определения команды Django для запуска development сервера.

Этот файл содержит класс Command, который наследуется от RunserverCommand и предоставляет 
функциональность для запуска сервера разработки с настройками хоста и порта из конфигурации.

Пример использования:
>>> python src/manage.py runserver [host:port]
"""

import logging

from django.core.management.commands.runserver import Command as RunserverCommand
from django.core.management.base import CommandParser

from django.conf import settings

logger = logging.getLogger('core.utils.commands')

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
        logger.info('Запуск команды runserver')
        
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
            super().handle(*args, **options)
        except Exception as e:
            msg = f'Ошибка при запуске сервера: {str(e)}'
            logger.error(msg)
            raise