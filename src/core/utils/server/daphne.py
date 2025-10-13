"""
Файл для управления процессом Daphne сервера.

Этот файл содержит класс Daphne, который предоставляет функциональность для:
- Поиска процессов по имени
- Запуска Daphne сервера
- Остановки процессов
- Проверки статуса работы процесса

Пример использования:
>>> from src.core.utils.server.daphne import Daphne
>>> daphne = Daphne()
>>> process = daphne.start_daphne(LogLevel.INFO)
>>> is_running = daphne.is_process_running(process)
>>> daphne.stop_process('daphne')
"""

import subprocess
import threading
import psutil
import logging

from typing import Optional, List, Any

from django.conf import settings

from src.core.utils.enums import LogLevel

logger = logging.getLogger('core.utils.server')

class Daphne:
    """
    Класс для управления Daphne сервером.

    Предоставляет методы для запуска, остановки и мониторинга
    процесса Daphne сервера.
    """

    def find_process(self, process_name: str) -> Optional[psutil.Process]:
        """
        Поиск процесса по имени.

        Args:
            process_name: Имя искомого процесса

        Returns:
            Optional[psutil.Process]: Найденный процесс или None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if (process_name in proc.info['name'] or 
                    (proc.info['cmdline'] and 
                    any(process_name in arg for arg in proc.info['cmdline']))):
                    logger.debug(f'Найден процесс {process_name}: PID={proc.pid}')
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')

        logger.debug(f'Процесс {process_name} не найден')
        return None

    def __stop_process(self, process: psutil.Process) -> bool:
        """
        Остановка указанного процесса.

        Args:
            process: Процесс для остановки

        Returns:
            bool: True если процесс успешно остановлен
        """
        try:
            process.terminate()
            process.wait(timeout=5)
            logger.info(f'Процесс PID={process.pid} успешно остановлен')
            return True
        except Exception as e:
            logger.error(f"Ошибка при остановке процесса: {e}")
            return False

    def stop_process(self, process_name: str) -> bool:
        """
        Поиск и остановка процесса по имени.

        Args:
            process_name: Имя процесса для остановки

        Returns:
            bool: True если процесс найден и успешно остановлен
        """
        daphne_process = self.find_process(process_name)

        if daphne_process:
            logger.info(f'Остановка процесса {process_name}')
            return self.__stop_process(daphne_process)
        
        logger.warning(f'Процесс {process_name} не найден для остановки')
        return False

    def start_daphne(self, log_level: LogLevel = LogLevel.INFO) -> subprocess.Popen:
        """
        Запуск Daphne сервера.

        Args:
            log_level: Уровень логирования для сервера

        Returns:
            subprocess.Popen: Запущенный процесс сервера

        Raises:
            ValueError: Если не настроены необходимые параметры сервера
        """
        server_process_name = getattr(settings, 'SERVER_PROCESS_NAME', None)
        server_port = getattr(settings, 'SERVER_PORT', None)
        server_host = getattr(settings, 'SERVER_HOST', None)

        if not all([server_process_name, server_port, server_host]):
            msg = 'Не все параметры сервера настроены в конфигурации'
            logger.error(msg)
            raise ValueError(msg)

        cmd: List[str] = [
            server_process_name, 
            '-p', server_port, 
            '-b', server_host, 
            'src.config.asgi:application'
        ]

        logger.info(f'Запуск Daphne сервера с командой: {" ".join(cmd)}')
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        self._start_output_threads(process, log_level)
        return process
    
    def _start_output_threads(self, process: subprocess.Popen, log_level: LogLevel) -> None:
        """
        Запуск потоков для чтения вывода процесса.

        Args:
            process: Процесс для мониторинга
            log_level: Уровень логирования для вывода
        """
        def read_output(pipe: Any, log_level: LogLevel) -> None:
            """
            Чтение и логирование вывода из потока.

            Args:
                pipe: Поток для чтения
                log_level: Уровень логирования
            """
            for line in iter(pipe.readline, ''):
                if log_level == LogLevel.ERROR and 'ERROR' in line:
                    logger.error(line.strip())
                elif log_level == LogLevel.WARNING and 'WARNING' in line:
                    logger.warning(line.strip())
                elif log_level == LogLevel.INFO:
                    logger.info(line.strip())
                elif log_level == LogLevel.NONE:
                    continue

        stdout_thread = threading.Thread(
            target=read_output, 
            args=(process.stdout, log_level)
        )
        stdout_thread.start()

        stderr_thread = threading.Thread(
            target=read_output, 
            args=(process.stderr, log_level)
        )
        stderr_thread.start()
    
    def is_process_running(self, process: subprocess.Popen) -> bool:
        """
        Проверка работает ли процесс.

        Args:
            process: Процесс для проверки

        Returns:
            bool: True если процесс запущен и активен
        """
        try:
            psutil_process = psutil.Process(process.pid)
            return psutil_process.is_running() and psutil_process.status() != psutil.STATUS_ZOMBIE
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False