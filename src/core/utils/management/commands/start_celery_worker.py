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

from pathlib import Path
from typing import Optional, List, cast

from django.core.management.base import BaseCommand, CommandParser
from src.core.utils.celery.manager import CeleryModuleManager

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
        parser.add_argument(
            '--queues',
            type=str,
            default=None,
            help='Список очередей через запятую. Если не указано, используются все очереди из модулей.'
        )
        parser.add_argument(
            '--hostname',
            type=str,
            default=None,
            help='Имя worker\'а для идентификации (по умолчанию генерируется автоматически на основе очередей)'
        )
        parser.add_argument(
            '--concurrency',
            type=int,
            default=None,
            help='Количество параллельных потоков для обработки задач (по умолчанию: 8 для thread pool)'
        )

    def find_celery_worker(self, queues: Optional[str] = None, hostname: Optional[str] = None) -> Optional[psutil.Process]:
        """
        Ищет запущенный процесс Celery worker с указанными очередями.

        Args:
            queues: Список очередей через запятую для поиска конкретного worker'а
            hostname: Имя worker'а для поиска конкретного worker'а

        Returns:
            Optional[psutil.Process]: Объект процесса если worker запущен, иначе None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                cmdline_str = ' '.join(cmdline)
                cmdline_lower = [part.lower() for part in cmdline]
                
                # Должны быть оба слова: 'celery' И 'worker'
                if 'celery' in cmdline_lower and 'worker' in cmdline_lower:
                    # Если указаны очереди, проверяем, что worker слушает эти очереди
                    if queues:
                        # Ищем параметр -Q в командной строке
                        queue_index = -1
                        for i, arg in enumerate(cmdline):
                            if arg == '-Q' and i + 1 < len(cmdline):
                                worker_queues = set(cmdline[i + 1].lower().split(','))
                                requested_queues = set(q.strip().lower() for q in queues.split(','))
                                # Проверяем, что все запрошенные очереди есть в worker'е
                                if requested_queues.issubset(worker_queues):
                                    logger.debug(f'Найден процесс Celery worker с очередями {queues}: PID={proc.pid}')
                                    return proc
                                break
                    # Если указан hostname, проверяем его
                    elif hostname:
                        if f'--hostname={hostname}' in cmdline_str or f'-n {hostname}' in cmdline_str:
                            logger.debug(f'Найден процесс Celery worker с hostname {hostname}: PID={proc.pid}')
                            return proc
                    # Если не указаны ни очереди, ни hostname, возвращаем первый найденный worker
                    else:
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
            **options: Именованные аргументы, включая loglevel, queues, hostname
        """
        queues: Optional[str] = cast(Optional[str], options.get('queues'))
        hostname: Optional[str] = cast(Optional[str], options.get('hostname'))
        
        logger.info(f'Запуск команды start_celery_worker (queues={queues}, hostname={hostname})')
        
        # Проверяем, не запущен ли уже worker с такими же очередями или hostname
        if self.find_celery_worker(queues=queues, hostname=hostname):
            msg = f'Celery worker с указанными параметрами уже запущен'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
            return

        # Определяем рабочую директорию (core/api/)
        api_dir = Path(__file__).resolve().parents[5]  # Путь к core/api/
        
        # Получаем все очереди из модулей
        module_manager = CeleryModuleManager()
        all_queues = module_manager.get_all_task_queues()
        
        # Формируем список очередей
        if queues:
            # Используем указанные очереди
            queue_names = set(q.strip() for q in str(queues).split(','))
            # Проверяем, что все указанные очереди существуют
            available_queues = set(all_queues.keys())
            invalid_queues = queue_names - available_queues
            if invalid_queues:
                msg = f'Неизвестные очереди: {", ".join(invalid_queues)}. Доступные очереди: {", ".join(sorted(available_queues))}'
                logger.error(msg)
                self.stdout.write(self.style.ERROR(msg))
                return
        else:
            # Используем все очереди из модулей (всегда включаем default)
            queue_names = set(['default'])  # Очередь по умолчанию всегда должна быть
            queue_names.update(all_queues.keys())  # Добавляем все очереди из модулей
        
        # Сортируем для консистентности
        queue_list = sorted(queue_names)
        queues_str = ','.join(queue_list)
        
        # Генерируем hostname, если не указан
        if not hostname:
            # Создаем уникальное имя на основе очередей
            queue_suffix = '_'.join(sorted(queue_list))[:50]  # Ограничиваем длину
            hostname = f'worker@{queue_suffix}'
        
        logger.info(f'Очереди для worker: {queues_str}')
        logger.info(f'Hostname worker: {hostname}')
        
        cmd: List[str] = [
            sys.executable,
            '-m',
            'celery',
            '-A',
            'src',
            'worker',
            '-Q', queues_str,
            f'--hostname={hostname}',
            f'--loglevel={options["loglevel"]}',
            '--pool=threads',
            '-E',
        ]
        
        # Добавляем параметр concurrency, если указан
        concurrency = options.get('concurrency')
        if concurrency:
            cmd.append(f'--concurrency={concurrency}')
        
        try:
            logger.info(f'Запуск Celery worker с командой: {" ".join(cmd)}')
            logger.info(f'Рабочая директория: {api_dir}')
            self.stdout.write(self.style.SUCCESS(f'Запуск Celery worker для очередей: {queues_str}'))
            subprocess.run(cmd, cwd=str(api_dir))
        except KeyboardInterrupt:
            logger.info('Получен сигнал прерывания, завершение работы')
            sys.exit(0)
        except Exception as e:
            logger.error(f'Ошибка при запуске Celery worker: {e}')
            raise 