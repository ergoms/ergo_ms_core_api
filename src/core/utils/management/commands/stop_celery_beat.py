"""
Файл для определения команды Django для остановки Celery beat scheduler.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для поиска и остановки запущенного процесса Celery beat.

Пример использования:
>>> python src/manage.py celery_beat_stop
"""

import logging
import psutil

from typing import Optional

from django.core.management.base import BaseCommand

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для остановки Celery beat scheduler.
    
    Находит и останавливает запущенный процесс Celery beat используя psutil.
    Использует SIGTERM для корректного завершения процесса.
    """
    help = 'Останавливает Celery beat scheduler'

    def find_celery_beat(self) -> Optional[psutil.Process]:
        """
        Ищет запущенный процесс Celery beat.

        Returns:
            Optional[psutil.Process]: Объект процесса если beat запущен, иначе None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                cmdline_lower = [part.lower() for part in cmdline]

                # Совпадение 1: стандартный процесс Celery beat
                # Должны быть оба слова: 'celery' И 'beat'
                is_celery_beat = ('celery' in cmdline_lower and 'beat' in cmdline_lower)

                # Совпадение 2: процесс запуска через обертку "api start_celery_beat"
                is_wrapper_beat = ('start_celery_beat' in cmdline_lower)

                # Сначала отдаем приоритет реальному celery-процессу
                if is_celery_beat:
                    logger.debug(
                        f"Найден процесс Celery beat: PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc

                # Если celery не найден, падаем обратно на обертку
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