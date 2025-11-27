"""
Файл для определения команды Django для остановки Celery worker.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для поиска и остановки запущенного процесса Celery worker.

Пример использования:
>>> python src/manage.py celery_worker_stop
"""

import psutil
import logging

from typing import Optional, List, cast

from django.core.management.base import BaseCommand, CommandParser

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для остановки Celery worker.
    
    Находит и останавливает запущенный процесс Celery worker используя psutil.
    Использует SIGTERM для корректного завершения процесса.
    """
    help = 'Останавливает Celery worker'

    def add_arguments(self, parser) -> None:
        """
        Добавляет аргументы командной строки.

        Args:
            parser: Парсер аргументов командной строки
        """
        parser.add_argument(
            '--queues',
            type=str,
            default=None,
            help='Список очередей через запятую для остановки конкретного worker\'а'
        )
        parser.add_argument(
            '--hostname',
            type=str,
            default=None,
            help='Имя worker\'а для остановки конкретного worker\'а'
        )
        parser.add_argument(
            '--all',
            action='store_true',
            help='Остановить все запущенные worker\'ы'
        )

    def find_celery_worker(self, queues: Optional[str] = None, hostname: Optional[str] = None) -> Optional[psutil.Process]:
        """
        Ищет запущенный процесс Celery worker с указанными параметрами.

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

                # Совпадение 1: стандартный процесс Celery worker
                # Должны быть оба слова: 'celery' И 'worker'
                is_celery_worker = ('celery' in cmdline_lower and 'worker' in cmdline_lower)

                # Совпадение 2: процесс запуска через обертку "api start_celery_worker"
                is_wrapper_worker = ('start_celery_worker' in cmdline_lower)

                # Сначала отдаем приоритет реальному celery-процессу
                if is_celery_worker:
                    # Если указаны очереди, проверяем, что worker слушает эти очереди
                    if queues:
                        # Ищем параметр -Q в командной строке
                        for i, arg in enumerate(cmdline):
                            if arg == '-Q' and i + 1 < len(cmdline):
                                worker_queues = set(cmdline[i + 1].lower().split(','))
                                requested_queues = set(q.strip().lower() for q in queues.split(','))
                                # Проверяем, что все запрошенные очереди есть в worker'е
                                if requested_queues.issubset(worker_queues):
                                    logger.debug(
                                        f"Найден процесс Celery worker с очередями {queues}: PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                                    )
                                    return proc
                                break
                    # Если указан hostname, проверяем его
                    elif hostname:
                        if f'--hostname={hostname}' in cmdline_str or f'-n {hostname}' in cmdline_str:
                            logger.debug(
                                f"Найден процесс Celery worker с hostname {hostname}: PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                            )
                            return proc
                    # Если не указаны ни очереди, ни hostname, возвращаем первый найденный worker
                    else:
                        logger.debug(
                            f"Найден процесс Celery worker: PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                        )
                        return proc

                # Если celery не найден, падаем обратно на обертку
                if is_wrapper_worker:
                    logger.debug(
                        f"Найден процесс Celery worker (обертка): PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')
                continue
        logger.debug('Процесс Celery worker не найден')
        return None

    def find_all_celery_workers(self) -> List[psutil.Process]:
        """
        Ищет все запущенные процессы Celery worker.

        Returns:
            List[psutil.Process]: Список процессов worker'ов
        """
        workers = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                cmdline_lower = [part.lower() for part in cmdline]

                # Совпадение 1: стандартный процесс Celery worker
                is_celery_worker = ('celery' in cmdline_lower and 'worker' in cmdline_lower)

                # Совпадение 2: процесс запуска через обертку "api start_celery_worker"
                is_wrapper_worker = ('start_celery_worker' in cmdline_lower)

                if is_celery_worker or is_wrapper_worker:
                    workers.append(proc)
                    logger.debug(
                        f"Найден процесс Celery worker: PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')
                continue
        return workers

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду остановки Celery worker.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы, включая queues, hostname, all
        """
        queues: Optional[str] = cast(Optional[str], options.get('queues'))
        hostname: Optional[str] = cast(Optional[str], options.get('hostname'))
        stop_all: bool = cast(bool, options.get('all', False))
        
        logger.info(f'Запуск команды stop_celery_worker (queues={queues}, hostname={hostname}, all={stop_all})')
        
        if stop_all:
            # Останавливаем все worker'ы
            workers = self.find_all_celery_workers()
            if not workers:
                msg = 'Запущенные Celery worker процессы не найдены'
                logger.warning(msg)
                self.stdout.write(self.style.WARNING(msg))
                return
            
            stopped_count = 0
            for process in workers:
                try:
                    logger.info(f'Остановка Celery worker (PID: {process.pid})')
                    process.terminate()
                    process.wait(timeout=5)
                    stopped_count += 1
                    msg = f'Celery worker процесс (PID: {process.pid}) успешно остановлен'
                    logger.info(msg)
                    self.stdout.write(self.style.SUCCESS(msg))
                except Exception as e:
                    msg = f'Ошибка при остановке Celery worker (PID: {process.pid}): {str(e)}'
                    logger.error(msg)
                    self.stdout.write(self.style.ERROR(msg))
            
            msg = f'Остановлено worker\'ов: {stopped_count} из {len(workers)}'
            self.stdout.write(self.style.SUCCESS(msg))
        else:
            # Останавливаем конкретный worker
            process = self.find_celery_worker(queues=queues, hostname=hostname)
            
            if process:
                try:
                    logger.info(f'Остановка Celery worker (PID: {process.pid})')
                    process.terminate()
                    process.wait(timeout=5)
                    msg = f'Celery worker процесс (PID: {process.pid}) успешно остановлен'
                    logger.info(msg)
                    self.stdout.write(self.style.SUCCESS(msg))
                except Exception as e:
                    msg = f'Ошибка при остановке Celery worker: {str(e)}'
                    logger.error(msg)
                    self.stdout.write(self.style.ERROR(msg))
            else:
                msg = 'Celery worker процесс не найден'
                logger.warning(msg)
                self.stdout.write(self.style.WARNING(msg))