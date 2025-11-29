"""
Файл для определения команды Django для запуска Celery worker.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для запуска процесса Celery worker с настройкой пула потоков и уровня логирования.

Пример использования:
>>> python src/manage.py start_celery_worker                 # Запустить все worker'ы из конфига
>>> python src/manage.py start_celery_worker --worker=gpu    # Запустить конкретный worker
>>> python src/manage.py start_celery_worker --queues=video_analysis  # Запустить для конкретных очередей
"""

import subprocess
import sys
import psutil
import logging
import yaml

from pathlib import Path
from typing import Optional, List, Dict, Any, cast

from django.core.management.base import BaseCommand, CommandParser
from src.core.utils.celery.manager import CeleryModuleManager
from src.config.settings.base import SYSTEM_DIR

logger = logging.getLogger('core.utils.commands')

# Путь к конфигу worker'ов
WORKERS_CONFIG_PATH = SYSTEM_DIR / 'celery_workers.yaml'


def load_workers_config() -> Dict[str, Any]:
    """Загружает конфигурацию worker'ов из YAML файла."""
    if not WORKERS_CONFIG_PATH.exists():
        logger.debug(f"Файл конфигурации worker'ов не найден: {WORKERS_CONFIG_PATH}")
        return {}
    
    try:
        with open(WORKERS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            return config or {}
    except Exception as e:
        logger.error(f"Ошибка загрузки конфигурации worker'ов: {e}")
        return {}

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
            '--worker',
            type=str,
            default=None,
            help='Имя worker\'а из celery_workers.yaml (gpu, cpu, parser, default, all). '
                 'Используйте --list-workers для списка доступных worker\'ов.'
        )
        parser.add_argument(
            '--list-workers',
            action='store_true',
            help='Показать список доступных worker\'ов из конфигурации'
        )
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

    def list_available_workers(self) -> None:
        """Выводит список доступных worker'ов из конфигурации."""
        config = load_workers_config()
        workers = config.get('workers', {})
        
        if not workers:
            self.stdout.write(self.style.WARNING(
                f"Конфигурация worker'ов не найдена. Создайте файл {WORKERS_CONFIG_PATH}"
            ))
            return
        
        self.stdout.write(self.style.SUCCESS("\nДоступные worker'ы из celery_workers.yaml:\n"))
        for name, worker_config in workers.items():
            description = worker_config.get('description', 'Без описания')
            queues = worker_config.get('queues', [])
            if queues == 'all':
                queues_str = 'все очереди'
            else:
                queues_str = ', '.join(queues) if queues else 'не указаны'
            concurrency = worker_config.get('concurrency', 'по умолчанию')
            hostname = worker_config.get('hostname', 'авто')
            
            self.stdout.write(f"  {self.style.NOTICE(name)}:")
            self.stdout.write(f"    Описание: {description}")
            self.stdout.write(f"    Очереди: {queues_str}")
            self.stdout.write(f"    Concurrency: {concurrency}")
            self.stdout.write(f"    Hostname: {hostname}")
            self.stdout.write("")
        
        self.stdout.write(self.style.SUCCESS(
            "Использование: api start_celery_worker --worker=<имя>\n"
        ))

    def build_worker_command(
        self, 
        queues_str: str, 
        hostname: str, 
        loglevel: str, 
        concurrency: Optional[int] = None
    ) -> List[str]:
        """Формирует команду для запуска одного worker'а."""
        cmd: List[str] = [
            sys.executable,
            '-m',
            'celery',
            '-A',
            'src',
            'worker',
            '-Q', queues_str,
            f'--hostname={hostname}',
            f'--loglevel={loglevel}',
            '--pool=threads',
            '-E',
        ]
        if concurrency:
            cmd.append(f'--concurrency={concurrency}')
        return cmd

    def start_single_worker(
        self, 
        api_dir: Path, 
        queues_str: str, 
        hostname: str, 
        loglevel: str,
        concurrency: Optional[int] = None,
        background: bool = False
    ) -> Optional[subprocess.Popen]:
        """
        Запускает один worker.
        
        Args:
            api_dir: Рабочая директория
            queues_str: Строка очередей через запятую
            hostname: Имя worker'а
            loglevel: Уровень логирования
            concurrency: Количество потоков
            background: Запускать в фоне
            
        Returns:
            Popen объект если background=True, иначе None
        """
        cmd = self.build_worker_command(queues_str, hostname, loglevel, concurrency)
        
        logger.info(f'Запуск Celery worker: {" ".join(cmd)}')
        self.stdout.write(self.style.SUCCESS(f'  Запуск worker "{hostname}" для очередей: {queues_str}'))
        
        if background:
            # Запускаем в фоне
            process = subprocess.Popen(
                cmd, 
                cwd=str(api_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            return process
        else:
            subprocess.run(cmd, cwd=str(api_dir))
            return None

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду запуска Celery worker.

        Поведение:
        - Без параметров: запускает все worker'ы из celery_workers.yaml (или один worker со всеми очередями если yaml нет)
        - --worker=<имя>: запускает конкретный worker из yaml
        - --queues=<очереди>: запускает worker для указанных очередей
        """
        # Показать список worker'ов
        if options.get('list_workers'):
            self.list_available_workers()
            return
        
        # Загружаем конфиг
        config = load_workers_config()
        defaults = config.get('defaults', {})
        workers_config = config.get('workers', {})
        
        # Определяем рабочую директорию (core/api/)
        api_dir = Path(__file__).resolve().parents[5]
        
        # Получаем все очереди из модулей
        module_manager = CeleryModuleManager()
        all_module_queues = module_manager.get_all_task_queues()
        
        worker_name = cast(Optional[str], options.get('worker'))
        queues_option = cast(Optional[str], options.get('queues'))
        hostname_option = cast(Optional[str], options.get('hostname'))
        concurrency_option = cast(Optional[int], options.get('concurrency'))
        loglevel_option = cast(str, options.get('loglevel', 'info'))
        
        # Режим 1: Указан конкретный worker из конфига
        if worker_name:
            if worker_name not in workers_config:
                available = ', '.join(workers_config.keys()) if workers_config else 'нет'
                self.stdout.write(self.style.ERROR(
                    f"Worker '{worker_name}' не найден. Доступные: {available}"
                ))
                return
            
            self._start_worker_from_config(
                str(worker_name),
                workers_config[worker_name], 
                defaults, 
                api_dir, 
                all_module_queues
            )
            return
        
        # Режим 2: Указаны очереди напрямую
        if queues_option or hostname_option:
            self._start_worker_direct(
                api_dir, 
                all_module_queues,
                queues_option, 
                hostname_option, 
                loglevel_option, 
                concurrency_option
            )
            return
        
        # Режим 3: Нет параметров — запускаем все worker'ы из конфига
        if workers_config:
            self._start_all_workers(workers_config, defaults, api_dir, all_module_queues)
        else:
            # Нет конфига — запускаем один worker со всеми очередями
            self.stdout.write(self.style.WARNING(
                f"Конфиг {WORKERS_CONFIG_PATH} не найден. Запуск worker'а со всеми очередями."
            ))
            self._start_worker_direct(api_dir, all_module_queues, None, None, loglevel_option, None)

    def _resolve_queues(
        self, 
        queues_config: Any, 
        all_module_queues: Dict[str, Any]
    ) -> List[str]:
        """Преобразует конфигурацию очередей в список строк."""
        if queues_config == 'all' or queues_config is None:
            queue_names = set(['default'])
            queue_names.update(all_module_queues.keys())
            return sorted(queue_names)
        elif isinstance(queues_config, list):
            return queues_config
        elif isinstance(queues_config, str):
            return [q.strip() for q in queues_config.split(',')]
        return []

    def _start_worker_from_config(
        self, 
        name: str, 
        worker_conf: Dict[str, Any], 
        defaults: Dict[str, Any],
        api_dir: Path,
        all_module_queues: Dict[str, Any]
    ) -> None:
        """Запускает один worker из конфигурации."""
        queues = self._resolve_queues(worker_conf.get('queues'), all_module_queues)
        hostname = worker_conf.get('hostname', f'worker@{name}')
        concurrency = worker_conf.get('concurrency')
        loglevel = worker_conf.get('loglevel', defaults.get('loglevel', 'info'))
        
        description = worker_conf.get('description', '')
        self.stdout.write(self.style.SUCCESS(f"\nЗапуск worker '{name}': {description}"))
        
        # Проверяем не запущен ли уже
        queues_str = ','.join(queues)
        if self.find_celery_worker(hostname=hostname):
            self.stdout.write(self.style.WARNING(f"Worker '{hostname}' уже запущен"))
            return
        
        try:
            self.start_single_worker(api_dir, queues_str, hostname, loglevel, concurrency, background=False)
        except KeyboardInterrupt:
            logger.info('Получен сигнал прерывания')
            sys.exit(0)

    def _start_worker_direct(
        self,
        api_dir: Path,
        all_module_queues: Dict[str, Any],
        queues: Optional[str],
        hostname: Optional[str],
        loglevel: str,
        concurrency: Optional[int]
    ) -> None:
        """Запускает worker с указанными параметрами напрямую."""
        if queues:
            queue_names = set(q.strip() for q in queues.split(','))
            available_queues = set(all_module_queues.keys())
            invalid_queues = queue_names - available_queues - {'default'}
            if invalid_queues:
                self.stdout.write(self.style.ERROR(
                    f'Неизвестные очереди: {", ".join(invalid_queues)}. '
                    f'Доступные: {", ".join(sorted(available_queues))}'
                ))
                return
            queue_list = sorted(queue_names)
        else:
            queue_list = sorted(set(['default']) | set(all_module_queues.keys()))
        
        queues_str = ','.join(queue_list)
        
        if not hostname:
            queue_suffix = '_'.join(queue_list)[:50]
            hostname = f'worker@{queue_suffix}'
        
        if self.find_celery_worker(hostname=hostname):
            self.stdout.write(self.style.WARNING(f"Worker '{hostname}' уже запущен"))
            return
        
        self.stdout.write(self.style.SUCCESS(f"\nЗапуск Celery worker"))
        
        try:
            self.start_single_worker(api_dir, queues_str, hostname, loglevel, concurrency, background=False)
        except KeyboardInterrupt:
            logger.info('Получен сигнал прерывания')
            sys.exit(0)

    def _start_all_workers(
        self, 
        workers_config: Dict[str, Dict[str, Any]], 
        defaults: Dict[str, Any],
        api_dir: Path,
        all_module_queues: Dict[str, Any]
    ) -> None:
        """Запускает все worker'ы из конфигурации параллельно в фоне."""
        import time
        
        processes: List[subprocess.Popen] = []
        started_workers: List[str] = []
        
        self.stdout.write(self.style.SUCCESS(
            f"\nЗапуск {len(workers_config)} worker'ов из celery_workers.yaml...\n"
        ))
        
        for name, worker_conf in workers_config.items():
            queues = self._resolve_queues(worker_conf.get('queues'), all_module_queues)
            hostname = worker_conf.get('hostname', f'worker@{name}')
            concurrency = worker_conf.get('concurrency')
            loglevel = worker_conf.get('loglevel', defaults.get('loglevel', 'info'))
            
            # Проверяем не запущен ли уже
            if self.find_celery_worker(hostname=hostname):
                self.stdout.write(self.style.WARNING(f"  Worker '{hostname}' уже запущен, пропуск"))
                continue
            
            queues_str = ','.join(queues)
            cmd = self.build_worker_command(queues_str, hostname, loglevel, concurrency)
            
            self.stdout.write(f"  Запуск '{name}' ({hostname}) -> очереди: {queues_str}")
            
            proc = subprocess.Popen(
                cmd, 
                cwd=str(api_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                start_new_session=True
            )
            processes.append(proc)
            started_workers.append(hostname)
            
            time.sleep(0.3)
        
        if not processes:
            self.stdout.write(self.style.WARNING("Нет worker'ов для запуска"))
            return
        
        self.stdout.write(self.style.SUCCESS(
            f"\nЗапущено {len(processes)} worker'ов: {', '.join(started_workers)}"
        ))
        self.stdout.write("Нажмите Ctrl+C для остановки...\n")
        
        # Ждем завершения
        try:
            while True:
                alive = [p for p in processes if p.poll() is None]
                if not alive:
                    self.stdout.write(self.style.WARNING("Все worker'ы завершились"))
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nОстановка worker'ов..."))
            for proc in processes:
                if proc.poll() is None:
                    proc.terminate()
            time.sleep(2)
            for proc in processes:
                if proc.poll() is None:
                    proc.kill()
            self.stdout.write(self.style.SUCCESS("Worker'ы остановлены")) 