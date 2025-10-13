"""
Файл для определения команды Django для очистки системного кэша.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для очистки кэша Django через стандартный интерфейс кэширования.

Пример использования:
>>> python src/manage.py clear_cache
"""

import logging

from django.core.management.base import BaseCommand
from django.core.cache import cache

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для очистки системного кэша.
    
    Использует стандартный интерфейс кэширования Django для
    полной очистки всего кэша.
    """
    help = 'Очистка системного кэша'

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду очистки кэша.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        logger.info('Запуск команды clear_cache')
        try:
            cache.clear()
            msg = 'Кэш успешно очищен'
            logger.info(msg)
            self.stdout.write(self.style.SUCCESS(msg))
        except Exception as e:
            msg = f'Ошибка при очистке кэша: {str(e)}'
            logger.error(msg)
            self.stdout.write(self.style.ERROR(msg))