"""
Файл для определения команды Django для остановки Celery beat scheduler.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для поиска и остановки запущенного процесса Celery beat.

Пример использования:
>>> ergoms api stop_celery_beat
"""

import logging
import psutil

from typing import Optional

from django.core.management.base import BaseCommand

from src.core.utils.os_abstraction import get_os_abstraction

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для остановки Celery beat scheduler.
    
    Находит и останавливает запущенный процесс Celery beat используя psutil.
    Использует SIGTERM для корректного завершения процесса.
    """
    help = 'Останавливает Celery beat scheduler'

    @staticmethod
    def _is_celery_cmd(cmdline: list) -> bool:
        """Проверяет, что cmdline — реальный процесс Celery, а не grep/cat и т.п."""
        if len(cmdline) < 2:
            return False
        first = str(cmdline[0]).lower()
        names = get_os_abstraction().process_executable_names('celery')
        return 'python' in first or any(first.endswith(n) for n in names)

    def find_celery_beat(self) -> Optional[psutil.Process]:
        """
        Ищет запущенный процесс Celery beat.

        Returns:
            Optional[psutil.Process]: Объект процесса если beat запущен, иначе None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                if not self._is_celery_cmd(cmdline):
                    continue
                cmdline_lower = [part.lower() for part in cmdline]

                is_celery_beat = 'beat' in cmdline_lower
                is_wrapper_beat = any('start_celery_beat' in part for part in cmdline_lower)

                if is_celery_beat:
                    logger.debug(
                        f"Найден процесс Celery beat: PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc

                if is_wrapper_beat:
                    logger.debug(
                        f"Найден процесс Celery beat (обертка): PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')
                continue
        logger.debug('Процесс Celery beat не найден')
        return None

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду остановки Celery beat.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        logger.info('Запуск команды celery_beat_stop')
        process = self.find_celery_beat()
        
        if process:
            try:
                logger.info(f'Остановка Celery beat (PID: {process.pid})')
                process.terminate()
                process.wait(timeout=5)
                msg = f'Celery beat процесс (PID: {process.pid}) успешно остановлен'
                logger.info(msg)
                self.stdout.write(self.style.SUCCESS(msg))
            except Exception as e:
                msg = f'Ошибка при остановке Celery beat: {str(e)}'
                logger.error(msg)
                self.stdout.write(self.style.ERROR(msg))
        else:
            msg = 'Celery beat процесс не найден'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg)) 