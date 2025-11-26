"""
Файл для определения команды Django для остановки development сервера.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для поиска и остановки запущенного процесса Django development сервера.

Пример использования:
>>> python src/manage.py stop_dev
"""

import logging
import psutil

from typing import Optional

from django.core.management.base import BaseCommand

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для остановки development сервера.
    
    Находит и останавливает запущенный процесс Django runserver используя psutil.
    Использует SIGTERM для корректного завершения процесса.
    """
    help = 'Останавливает development сервер'

    def find_dev_server(self) -> Optional[psutil.Process]:
        """
        Ищет запущенный процесс Django development сервера.

        Returns:
            Optional[psutil.Process]: Объект процесса если сервер запущен, иначе None
        """
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = proc.info.get('cmdline') or []
                # На Linux cmdline - это список, на Windows может быть строка или список
                # Нормализуем к списку для универсальности
                if isinstance(cmdline, str):
                    cmdline = [cmdline]
                
                cmdline_lower = [part.lower() for part in cmdline]
                # Создаем единую строку для поиска (работает на Linux и Windows)
                cmdline_str = ' '.join(cmdline).lower()

                # Исключаем процессы других серверов
                excluded_keywords = ['celery', 'daphne', 'gunicorn', 'uvicorn']
                if any(x in cmdline_str for x in excluded_keywords):
                    continue

                # Совпадение 1: стандартный процесс Django runserver
                # Должны быть оба слова: 'manage.py' И 'runserver'
                is_runserver = ('manage.py' in cmdline_lower and 'runserver' in cmdline_lower)

                # Совпадение 2: процесс запуска через обертку "api dev"
                # На Linux: ['python', '/path/to/api', 'dev'] - отдельные элементы
                # На Windows: может быть ['python api dev'] или ['python', 'api', 'dev']
                # Ищем элемент, который заканчивается на 'api' (команда или путь к скрипту)
                # и проверяем, что следующий элемент или часть строки содержит 'dev'
                is_wrapper_dev = False
                for i, part in enumerate(cmdline_lower):
                    # Проверяем, что элемент заканчивается на 'api' или содержит 'api' как отдельное слово
                    if part.endswith('api') or part.endswith('/api') or part.endswith('\\api'):
                        # Проверяем следующий элемент или всю строку после этого элемента
                        if i + 1 < len(cmdline_lower):
                            # Следующий элемент содержит 'dev'
                            if 'dev' in cmdline_lower[i + 1]:
                                is_wrapper_dev = True
                                break
                        # Или проверяем всю строку - 'dev' должен идти после 'api'
                        remaining_str = ' '.join(cmdline_lower[i:])
                        if 'dev' in remaining_str:
                            is_wrapper_dev = True
                            break

                # Совпадение 3: процесс может содержать "runserver" в командной строке
                is_runserver_direct = 'runserver' in cmdline_str

                # Сначала отдаем приоритет реальному runserver процессу
                if is_runserver:
                    logger.debug(
                        f"Найден процесс Django runserver: PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc

                # Если runserver не найден, проверяем обертку
                if is_wrapper_dev:
                    logger.debug(
                        f"Найден процесс dev сервера (обертка): PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc

                # Последняя проверка - прямой поиск runserver
                if is_runserver_direct:
                    logger.debug(
                        f"Найден процесс runserver (прямой поиск): PID={proc.pid}, CMDLINE={' '.join(cmdline)}"
                    )
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')
                continue
        logger.debug('Процесс development сервера не найден')
        return None

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду остановки development сервера.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы
        """
        logger.info('Запуск команды stop_dev')
        process = self.find_dev_server()
        
        if process:
            try:
                logger.info(f'Остановка development сервера (PID: {process.pid})')
                process.terminate()
                process.wait(timeout=5)
                msg = f'Development сервер (PID: {process.pid}) успешно остановлен'
                logger.info(msg)
                self.stdout.write(self.style.SUCCESS(msg))
            except Exception as e:
                msg = f'Ошибка при остановке development сервера: {str(e)}'
                logger.error(msg)
                self.stdout.write(self.style.ERROR(msg))
        else:
            msg = 'Development сервер не найден'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))

