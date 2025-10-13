"""
Файл для определения команды Django для остановки Daphne сервера.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для остановки запущенного процесса Daphne сервера.

Пример использования:
>>> python src/manage.py stop_prod
"""

import logging

from django.core.management.base import BaseCommand
from django.conf import settings

from src.core.utils.server.daphne import Daphne

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для остановки production сервера.
    
    Находит и останавливает запущенный процесс Daphne сервера используя
    имя процесса из настроек Django.
    """
    help = "Остановка production сервера (Daphne)"

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду остановки сервера.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        logger.info('Запуск команды stop_prod')
        
        server_process_name = getattr(settings, 'SERVER_PROCESS_NAME', None)
        if not server_process_name:
            msg = 'SERVER_PROCESS_NAME не настроен в настройках Django'
            logger.error(msg)
            self.stdout.write(self.style.ERROR(msg))
            return

        daphne = Daphne()
        logger.info(f'Поиск процесса сервера: {server_process_name}')
        is_stopped = daphne.stop_process(server_process_name)

        if is_stopped:
            msg = 'Сервер успешно остановлен'
            logger.info(msg)
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            msg = 'Не удалось остановить сервер'
            logger.error(msg)
            self.stdout.write(self.style.ERROR(msg))