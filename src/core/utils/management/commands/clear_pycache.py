"""
Файл для определения команды Django для очистки Python кэша.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для рекурсивного удаления всех директорий __pycache__ в проекте.

Пример использования:
>>> python src/manage.py clear_pycache
"""

import os
import shutil
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для очистки Python кэша.
    
    Рекурсивно обходит все директории проекта и удаляет найденные
    директории __pycache__.
    """
    help = 'Очистка python кэша'

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду очистки Python кэша.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        logger.info('Запуск команды clear_pycache')
        root_directory = '.'

        for root, dirs, _ in os.walk(root_directory):
            for dir_name in dirs:
                if dir_name == '__pycache__':

                    dir_path = os.path.join(root, dir_name)
                    try:
                        shutil.rmtree(dir_path)
                        msg = f'Удалена директория: {dir_path}'

                        logger.info(msg)
                        self.stdout.write(self.style.SUCCESS(msg))
                    except Exception as e:
                        msg = f'Ошибка при удалении {dir_path}: {str(e)}'

                        logger.error(msg)
                        self.stdout.write(self.style.ERROR(msg))