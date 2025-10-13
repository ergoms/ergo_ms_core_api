"""
Файл для определения команды Django для запуска Celery worker.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для запуска процесса Celery worker с настройкой пула потоков и уровня логирования.

Пример использования:
>>> python src/manage.py start_celery_worker [--loglevel=info]
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
    Команда Django для запуска Celery worker.
    
    Проверяет наличие уже запущенного процесса и запускает новый процесс
    с указанным уровнем логирования и пулом потоков если процесс не найден.
    """
    help = 'Запускает Celery worker с настройками eventlet'

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

    def find_celery_worker(self) -> Optional[psutil.Process]:
        """
        Ищет запущенный процесс Celery worker.

        Returns:
            Optional[psutil.Process]: Объект процесса если worker запущен, иначе None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if (proc.info['cmdline'] and 
                    'celery' in proc.info['cmdline'] and 
                    'worker' in proc.info['cmdline']):
                    logger.debug(f'Найден процесс Celery worker: PID={proc.pid}')
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')
                continue
        logger.debug('Процесс Celery worker не найден')
        return None

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду запуска Celery worker.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы, включая loglevel
        """
        logger.info('Запуск команды start_celery_worker')
        
        if self.find_celery_worker():
            msg = 'Celery worker уже запущен'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
            return

        cmd: List[str] = [
            'celery',
            '-A',
            'src',
            'worker',
            f'--loglevel={options["loglevel"]}',
            '--pool=threads',
        ]
        
        try:
            logger.info(f'Запуск Celery worker с командой: {" ".join(cmd)}')
            self.stdout.write(self.style.SUCCESS('Запуск Celery worker...'))
            subprocess.run(cmd)
        except KeyboardInterrupt:
            logger.info('Получен сигнал прерывания, завершение работы')
            sys.exit(0)
        except Exception as e:
            logger.error(f'Ошибка при запуске Celery worker: {e}')
            raise 