"""
Файл для определения команды Django для остановки Celery worker.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для поиска и остановки запущенного процесса Celery worker.

Пример использования:
>>> python src/manage.py stop_celery_worker --all
>>> python src/manage.py stop_celery_worker --worker=gpu
>>> python src/manage.py stop_celery_worker --hostname=gpu_worker
"""

import psutil
import logging
import yaml

from typing import Optional, List, Dict, Any, cast
from pathlib import Path

from django.core.management.base import BaseCommand, CommandParser
from src.config.settings.base import SYSTEM_DIR

logger = logging.getLogger('core.utils.commands')

# Путь к конфигу worker'ов
WORKERS_CONFIG_PATH = SYSTEM_DIR / 'celery_workers.yaml'


def load_workers_config() -> Dict[str, Any]:
    """Загружает конфигурацию worker'ов из YAML файла."""
    if not WORKERS_CONFIG_PATH.exists():
        return {}
    try:
        with open(WORKERS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации worker'ов: {e}")
        return {}

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
            '--worker',
            type=str,
            default=None,
            help='Имя worker\'а из celery_workers.yaml (gpu, cpu, parser, default)'
        )
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
            default=True,
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
        seen_pids = set()
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                pid = proc.info.get('pid')
                if pid in seen_pids:
                    continue
                    
                cmdline = proc.info.get('cmdline') or []
                if not cmdline:
                    continue
                    
                cmdline_str = ' '.join(cmdline).lower()

                # Совпадение: celery worker процесс
                # Ищем "celery" и "worker" в командной строке
                is_celery_worker = ('celery' in cmdline_str and 'worker' in cmdline_str)

                if is_celery_worker:
                    workers.append(proc)
                    seen_pids.add(pid)
                    logger.debug(
                        f"Найден процесс Celery worker: PID={pid}, CMDLINE={' '.join(cmdline)}"
                    )
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        logger.info(f"Найдено {len(workers)} Celery worker процессов")
        return workers
    
    def find_workers_by_hostname(self, hostname: str) -> List[psutil.Process]:
        """
        Ищет процессы Celery worker по hostname.

        Args:
            hostname: Имя worker'а (hostname)

        Returns:
            List[psutil.Process]: Список найденных процессов
        """
        workers = []
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if not cmdline:
                    continue
                    
                cmdline_str = ' '.join(cmdline)
                cmdline_lower = cmdline_str.lower()

                # Проверяем что это celery worker
                if 'celery' not in cmdline_lower or 'worker' not in cmdline_lower:
                    continue
                
                # Проверяем hostname
                if f'--hostname={hostname}' in cmdline_str or f'-n {hostname}' in cmdline_str:
                    workers.append(proc)
                    logger.debug(f"Найден worker с hostname={hostname}: PID={proc.pid}")
                    
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        return workers

    def _stop_processes(self, processes: List[psutil.Process], label: str = "") -> int:
        """
        Останавливает список процессов.
        
        Args:
            processes: Список процессов для остановки
            label: Метка для логирования
            
        Returns:
            Количество успешно остановленных процессов
        """
        stopped_count = 0
        for process in processes:
            try:
                pid = process.pid
                logger.info(f'Остановка Celery worker {label}(PID: {pid})')
                process.terminate()
                try:
                    process.wait(timeout=5)
                except psutil.TimeoutExpired:
                    logger.warning(f'Таймаут при ожидании завершения PID={pid}, принудительное завершение')
                    process.kill()
                    process.wait(timeout=2)
                stopped_count += 1
                self.stdout.write(self.style.SUCCESS(f'  Остановлен PID={pid}'))
            except psutil.NoSuchProcess:
                self.stdout.write(self.style.WARNING(f'  Процесс PID={process.pid} уже завершен'))
                stopped_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'  Ошибка остановки PID={process.pid}: {e}'))
        return stopped_count

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду остановки Celery worker.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        worker_name: Optional[str] = cast(Optional[str], options.get('worker'))
        queues: Optional[str] = cast(Optional[str], options.get('queues'))
        hostname: Optional[str] = cast(Optional[str], options.get('hostname'))
        stop_all: bool = cast(bool, options.get('all', False))
        
        logger.info(f'Запуск команды stop_celery_worker (worker={worker_name}, queues={queues}, hostname={hostname}, all={stop_all})')
        
        # Режим 1: Остановить все worker'ы
        if stop_all:
            self.stdout.write("Поиск всех Celery worker'ов...")
            workers = self.find_all_celery_workers()
            
            if not workers:
                self.stdout.write(self.style.WARNING('Запущенные Celery worker процессы не найдены'))
                return
            
            self.stdout.write(f"Найдено {len(workers)} worker'ов, останавливаем...")
            stopped = self._stop_processes(workers)
            self.stdout.write(self.style.SUCCESS(f"\nОстановлено: {stopped} из {len(workers)}"))
            return
        
        # Режим 2: Остановить worker по имени из конфига
        if worker_name:
            config = load_workers_config()
            workers_config = config.get('workers', {})
            
            if worker_name not in workers_config:
                available = ', '.join(workers_config.keys()) if workers_config else 'нет'
                self.stdout.write(self.style.ERROR(f"Worker '{worker_name}' не найден. Доступные: {available}"))
                return
            
            worker_conf = workers_config[worker_name]
            target_hostname = worker_conf.get('hostname', f'worker@{worker_name}')
            
            self.stdout.write(f"Поиск worker'а '{worker_name}' (hostname={target_hostname})...")
            workers = self.find_workers_by_hostname(target_hostname)
            
            if not workers:
                self.stdout.write(self.style.WARNING(f"Worker '{worker_name}' не запущен"))
                return
            
            stopped = self._stop_processes(workers, f"'{worker_name}' ")
            self.stdout.write(self.style.SUCCESS(f"\nWorker '{worker_name}' остановлен ({stopped} процессов)"))
            return
        
        # Режим 3: Остановить по hostname
        if hostname:
            self.stdout.write(f"Поиск worker'ов с hostname={hostname}...")
            workers = self.find_workers_by_hostname(hostname)
            
            if not workers:
                self.stdout.write(self.style.WARNING(f"Worker с hostname={hostname} не найден"))
                return
            
            stopped = self._stop_processes(workers)
            self.stdout.write(self.style.SUCCESS(f"\nОстановлено: {stopped}"))
            return
        
        # Режим 4: Остановить по очередям
        if queues:
            process = self.find_celery_worker(queues=queues)
            if process:
                self._stop_processes([process])
                self.stdout.write(self.style.SUCCESS("Worker остановлен"))
            else:
                self.stdout.write(self.style.WARNING(f"Worker с очередями {queues} не найден"))
            return
        
        # Без параметров — показать справку
        self.stdout.write("Использование:")
        self.stdout.write("  --all              Остановить все worker'ы")
        self.stdout.write("  --worker=<имя>     Остановить worker из celery_workers.yaml")
        self.stdout.write("  --hostname=<имя>   Остановить worker по hostname")
        self.stdout.write("  --queues=<список>  Остановить worker по очередям")