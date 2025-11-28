"""
Файл для определения команды Django для остановки Ollama сервера.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для поиска и остановки запущенного процесса Ollama.

Пример использования:
>>> python src/manage.py stop_ollama
"""

import logging
import psutil

from typing import Optional

from django.core.management.base import BaseCommand

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для остановки Ollama сервера.
    
    Находит и останавливает запущенный процесс Ollama используя psutil.
    Использует SIGTERM для корректного завершения процесса.
    """
    help = 'Останавливает Ollama сервер'

    def find_ollama(self) -> Optional[psutil.Process]:
        """
        Ищет запущенный процесс Ollama.

        Returns:
            Optional[psutil.Process]: Объект процесса если Ollama запущен, иначе None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                cmdline_lower = [part.lower() for part in cmdline]

                # Совпадение 1: стандартный процесс Ollama serve
                is_ollama_serve = ('ollama' in cmdline_lower and 'serve' in cmdline_lower)

                # Совпадение 2: процесс запуска через обертку "api start_ollama"
                is_wrapper_ollama = ('start_ollama' in cmdline_lower)

                # Сначала отдаем приоритет реальному ollama-процессу
                if is_ollama_serve:
                    logger.debug(
                        f"Найден процесс Ollama: PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc

                # Если ollama не найден, падаем обратно на обертку
                if is_wrapper_ollama:
                    logger.debug(
                        f"Найден процесс Ollama (обертка): PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')
                continue
        logger.debug('Процесс Ollama не найден')
        return None

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду остановки Ollama.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        logger.info('Запуск команды stop_ollama')
        process = self.find_ollama()
        
        if process:
            try:
                logger.info(f'Остановка Ollama (PID: {process.pid})')
                process.terminate()
                process.wait(timeout=5)
                msg = f'Ollama процесс (PID: {process.pid}) успешно остановлен'
                logger.info(msg)
                self.stdout.write(self.style.SUCCESS(msg))
            except Exception as e:
                msg = f'Ошибка при остановке Ollama: {str(e)}'
                logger.error(msg)
                self.stdout.write(self.style.ERROR(msg))
        else:
            msg = 'Ollama процесс не найден'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
