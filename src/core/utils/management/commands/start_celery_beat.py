"""
Файл для определения команды Django для запуска Celery beat scheduler.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для запуска процесса Celery beat с настройкой уровня логирования.

Пример использования:
>>> python src/manage.py start_celery_beat [--loglevel=info]
"""

import subprocess
import sys
import psutil
import logging

from typing import Optional, List

from django.core.management.base import BaseCommand, CommandParser

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для запуска Celery beat scheduler.
    
    Проверяет наличие уже запущенного процесса и запускает новый процесс
    с указанным уровнем логирования если процесс не найден.
    """
    help = 'Запускает Celery beat scheduler'

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Добавляет аргументы командной строки.

        Args:
            parser: Парсер аргументов командной строки
        """
        parser.add_argument(
            '--loglevel',
            default='info',
            help='Уровень логирования (default: info)'
        )

    def find_celery_beat(self) -> Optional[psutil.Process]:
        """
        Ищет запущенный процесс Celery beat.

        Returns:
            Optional[psutil.Process]: Объект процесса если beat запущен, иначе None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if (proc.info['cmdline'] and 
                    'celery' in proc.info['cmdline'] and 
                    'beat' in proc.info['cmdline']):
                    logger.debug(f'Найден процесс Celery beat: PID={proc.pid}')
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')
                continue
        logger.debug('Процесс Celery beat не найден')
        return None

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду запуска Celery beat.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы, включая loglevel
        """
        logger.info('Запуск команды start_celery_beat')
        
        if self.find_celery_beat():
            msg = 'Celery beat уже запущен'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
            return

        cmd: List[str] = [
            'celery',
            '-A',
            'src',
            'beat',
            f'--loglevel={options["loglevel"]}'
        ]
        
        try:
            logger.info(f'Запуск Celery beat с командой: {" ".join(cmd)}')
            self.stdout.write(self.style.SUCCESS('Запуск Celery beat...'))
            subprocess.run(cmd)
        except KeyboardInterrupt:
            logger.info('Получен сигнал прерывания, завершение работы')
            sys.exit(0)
        except Exception as e:
            logger.error(f'Ошибка при запуске Celery beat: {e}')
            raise 