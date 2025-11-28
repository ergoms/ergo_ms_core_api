"""
Файл для определения команды Django для запуска Ollama сервера.

Этот файл содержит класс Command, который наследуется от BaseCommand и предоставляет 
функциональность для запуска процесса Ollama сервера с красивым форматированием логов
и отслеживанием метрик генерации токенов.

Пример использования:
>>> python src/manage.py start_ollama
"""

import subprocess
import sys
import psutil
import logging
import re
import json
from datetime import datetime
from threading import Thread
from queue import Queue, Empty

from pathlib import Path
from typing import Optional, List, Dict, Any

from django.core.management.base import BaseCommand, CommandParser

logger = logging.getLogger('core.utils.commands')

class Command(BaseCommand):
    """
    Команда Django для запуска Ollama сервера.
    
    Проверяет наличие уже запущенного процесса и запускает новый процесс
    если процесс не найден.
    """
    help = 'Запускает Ollama сервер'

    def add_arguments(self, parser: CommandParser) -> None:
        """
        Добавляет аргументы командной строки.

        Args:
            parser: Парсер аргументов командной строки
        """
        parser.add_argument(
            '--host',
            default=None,
            help='Хост для запуска Ollama (по умолчанию используется стандартный порт Ollama)'
        )
        parser.add_argument(
            '--port',
            default=None,
            help='Порт для запуска Ollama (по умолчанию используется стандартный порт Ollama)'
        )

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
                
                # Ищем процесс ollama serve
                if 'ollama' in cmdline_lower and 'serve' in cmdline_lower:
                    logger.debug(f'Найден процесс Ollama: PID={proc.pid}')
                    return proc
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.error(f'Ошибка при поиске процесса: {e}')
                continue
        logger.debug('Процесс Ollama не найден')
        return None

    def parse_ollama_log(self, line: str) -> Optional[Dict[str, Any]]:
        """
        Парсит строку лога Ollama в структурированный формат.

        Args:
            line: Строка лога от Ollama

        Returns:
            Словарь с распарсенными данными или None если не удалось распарсить
        """
        # Формат: time=2025-11-29T02:42:41.544+03:00 level=INFO source=routes.go:1511 msg="..."
        pattern = r'time=([^\s]+)\s+level=(\w+)\s+source=([^\s]+)\s+msg="([^"]*)"'
        match = re.match(pattern, line)
        
        if match:
            time_str, level, source, msg = match.groups()
            try:
                # Парсим время
                time_obj = datetime.fromisoformat(time_str.replace('+', '+').replace('Z', '+00:00'))
                time_formatted = time_obj.strftime('%H:%M:%S')
            except:
                time_formatted = time_str.split('T')[1].split('+')[0] if 'T' in time_str else time_str
            
            # Извлекаем дополнительные параметры
            extra_params = {}
            # Паттерн для параметров вида key=value или key="value"
            param_pattern = r'(\w+)=([^\s"]+|"[^"]*")'
            for param_match in re.finditer(param_pattern, line):
                key, value = param_match.groups()
                if key not in ['time', 'level', 'source', 'msg']:
                    # Убираем кавычки если есть
                    value_clean = value.strip('"')
                    extra_params[key] = value_clean
            
            return {
                'time': time_formatted,
                'level': level,
                'source': source,
                'message': msg,
                'extra': extra_params,
                'raw': line
            }
        
        return None

    def format_log_line(self, log_data: Dict[str, Any]) -> str:
        """
        Форматирует распарсенный лог в красивый вид.

        Args:
            log_data: Распарсенные данные лога

        Returns:
            Отформатированная строка для вывода
        """
        time_str = log_data['time']
        level = log_data['level']
        source = log_data['source']
        msg = log_data['message']
        extra = log_data['extra']
        
        # Цвета для уровней
        level_colors = {
            'INFO': 'CYAN',
            'WARN': 'YELLOW',
            'ERROR': 'RED',
            'DEBUG': 'MAGENTA'
        }
        
        # Форматируем источник (убираем путь, оставляем только имя файла)
        source_short = source.split('/')[-1] if '/' in source else source.split('\\')[-1]
        
        # Форматируем сообщение
        formatted_msg = msg
        
        # Обрабатываем специальные сообщения
        if 'Listening on' in msg:
            # Извлекаем адрес
            addr_match = re.search(r'Listening on ([^\s]+)', msg)
            if addr_match:
                addr = addr_match.group(1)
                addr_styled = self.style.SUCCESS(addr)  # type: ignore[attr-defined]
                formatted_msg = f"🚀 Сервер запущен на {addr_styled}"
        
        elif 'discovering available GPUs' in msg:
            formatted_msg = "🔍 Поиск доступных GPU..."
        
        elif 'inference compute' in msg:
            # Информация о GPU
            gpu_name = extra.get('description', 'Unknown GPU')
            total_vram = extra.get('total', 'N/A')
            available_vram = extra.get('available', 'N/A')
            formatted_msg = f"🎮 GPU: {gpu_name} | VRAM: {available_vram} / {total_vram}"
        
        elif 'entering low vram mode' in msg:
            total_vram = extra.get('total vram', 'N/A')
            formatted_msg = f"⚠️  Режим низкой VRAM (всего: {total_vram})"
        
        elif 'total blobs' in msg:
            total = extra.get('total', '0')
            formatted_msg = f"📦 Всего blob'ов: {total}"
        
        elif 'total unused blobs removed' in msg:
            removed = extra.get('total unused blobs removed', '0')
            formatted_msg = f"🧹 Удалено неиспользуемых blob'ов: {removed}"
        
        # Формируем итоговую строку
        level_color = level_colors.get(level, 'SUCCESS')
        level_styled = getattr(self.style, level_color, self.style.SUCCESS)(f"[{level}]")  # type: ignore[attr-defined]
        
        time_styled = self.style.HTTP_INFO(time_str)  # type: ignore[attr-defined]
        source_styled = self.style.HTTP_INFO(source_short)  # type: ignore[attr-defined]
        return f"{time_styled} {level_styled} {source_styled} {formatted_msg}"

    def track_generation_metrics(self, log_data: Dict[str, Any], metrics: Dict[str, Any]) -> None:
        """
        Отслеживает метрики генерации токенов из логов.

        Args:
            log_data: Распарсенные данные лога
            metrics: Словарь для хранения метрик
        """
        msg = log_data['message']
        extra = log_data['extra']
        raw_line = log_data.get('raw', '')
        
        # Ищем информацию о генерации токенов в разных форматах
        # Формат 1: eval_count и eval_duration в extra параметрах
        if 'eval_count' in extra or 'eval_duration' in extra:
            try:
                eval_count = int(extra.get('eval_count', 0))
                eval_duration_str = extra.get('eval_duration', '0')
                # Может быть в наносекундах или секундах
                if 'ns' in str(eval_duration_str):
                    eval_duration = float(str(eval_duration_str).replace('ns', '')) / 1e9
                elif 'ms' in str(eval_duration_str):
                    eval_duration = float(str(eval_duration_str).replace('ms', '')) / 1000
                else:
                    eval_duration = float(eval_duration_str) / 1e9  # предполагаем наносекунды
                
                if eval_duration > 0 and eval_count > 0:
                    tokens_per_sec = eval_count / eval_duration
                    metrics['last_tokens'] = eval_count
                    metrics['last_duration'] = eval_duration
                    metrics['last_tokens_per_sec'] = tokens_per_sec
                    metrics['total_tokens'] = metrics.get('total_tokens', 0) + eval_count
                    metrics['total_duration'] = metrics.get('total_duration', 0) + eval_duration
                    
                    # Выводим метрику
                    avg_tokens_per_sec = metrics['total_tokens'] / metrics['total_duration'] if metrics.get('total_duration', 0) > 0 else 0
                    self.stdout.write(
                        f"\n{self.style.SUCCESS('⚡ Генерация:')} "
                        f"{self.style.SUCCESS(f'{tokens_per_sec:.2f}')} токенов/сек "
                        f"(среднее: {self.style.SUCCESS(f'{avg_tokens_per_sec:.2f}')} токенов/сек) | "
                        f"Всего токенов: {self.style.SUCCESS(str(metrics['total_tokens']))}\n"
                    )
            except (ValueError, TypeError):
                pass
        
        # Формат 2: ищем в сырой строке паттерны типа "eval_count=123 eval_duration=456ns"
        eval_count_match = re.search(r'eval_count=(\d+)', raw_line)
        eval_duration_match = re.search(r'eval_duration=([\d.]+)(ns|ms|s)?', raw_line)
        
        if eval_count_match and eval_duration_match:
            try:
                eval_count = int(eval_count_match.group(1))
                duration_val = float(eval_duration_match.group(1))
                duration_unit = eval_duration_match.group(2) or 'ns'
                
                if duration_unit == 'ns':
                    eval_duration = duration_val / 1e9
                elif duration_unit == 'ms':
                    eval_duration = duration_val / 1000
                else:
                    eval_duration = duration_val
                
                if eval_duration > 0 and eval_count > 0:
                    tokens_per_sec = eval_count / eval_duration
                    metrics['last_tokens'] = eval_count
                    metrics['last_duration'] = eval_duration
                    metrics['last_tokens_per_sec'] = tokens_per_sec
                    metrics['total_tokens'] = metrics.get('total_tokens', 0) + eval_count
                    metrics['total_duration'] = metrics.get('total_duration', 0) + eval_duration
                    
                    # Выводим метрику
                    avg_tokens_per_sec = metrics['total_tokens'] / metrics['total_duration'] if metrics.get('total_duration', 0) > 0 else 0
                    self.stdout.write(
                        f"\n{self.style.SUCCESS('⚡ Генерация:')} "
                        f"{self.style.SUCCESS(f'{tokens_per_sec:.2f}')} токенов/сек "
                        f"(среднее: {self.style.SUCCESS(f'{avg_tokens_per_sec:.2f}')} токенов/сек) | "
                        f"Всего токенов: {self.style.SUCCESS(str(metrics['total_tokens']))}\n"
                    )
            except (ValueError, TypeError):
                pass

    def read_output(self, pipe, queue: Queue) -> None:
        """
        Читает вывод из pipe и помещает в очередь.

        Args:
            pipe: Pipe для чтения
            queue: Очередь для записи строк
        """
        try:
            for line in iter(pipe.readline, ''):
                if line:
                    queue.put(line.rstrip())
        finally:
            pipe.close()
            queue.put(None)

    def handle(self, *args: tuple, **options: dict) -> None:
        """
        Выполняет команду запуска Ollama с красивым форматированием логов.

        Args:
            *args: Позиционные аргументы
            **options: Именованные аргументы, включая host и port
        """
        logger.info('Запуск команды start_ollama')
        
        if self.find_ollama():
            msg = 'Ollama уже запущен'
            logger.warning(msg)
            self.stdout.write(self.style.WARNING(msg))
            return

        # Определяем рабочую директорию (core/api/)
        api_dir = Path(__file__).resolve().parents[5]  # Путь к core/api/
        
        cmd: List[str] = ['ollama', 'serve']
        
        # Добавляем опции только если они указаны
        if options.get('host'):
            cmd.extend(['--host', str(options['host'])])
        if options.get('port'):
            cmd.extend(['--port', str(options['port'])])
        
        try:
            logger.info(f'Запуск Ollama с командой: {" ".join(cmd)}')
            logger.info(f'Рабочая директория: {api_dir}')
            
            self.stdout.write(self.style.SUCCESS('\n╔════════════════════════════════════════╗'))
            self.stdout.write(self.style.SUCCESS('║   🦙 Запуск Ollama Server              ║'))
            self.stdout.write(self.style.SUCCESS('╚════════════════════════════════════════╝\n'))
            
            # Запускаем процесс с перехватом stdout/stderr
            process = subprocess.Popen(
                cmd,
                cwd=str(api_dir),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )
            
            # Очереди для чтения вывода
            output_queue = Queue()
            
            # Поток для чтения вывода
            output_thread = Thread(target=self.read_output, args=(process.stdout, output_queue))
            output_thread.daemon = True
            output_thread.start()
            
            # Метрики генерации
            metrics = {
                'total_tokens': 0,
                'total_duration': 0,
                'last_tokens': 0,
                'last_duration': 0,
                'last_tokens_per_sec': 0
            }
            
            # Читаем вывод в реальном времени
            while True:
                try:
                    line = output_queue.get(timeout=0.1)
                    if line is None:
                        break
                    
                    # Парсим лог
                    log_data = self.parse_ollama_log(line)
                    
                    if log_data:
                        # Отслеживаем метрики
                        self.track_generation_metrics(log_data, metrics)
                        
                        # Форматируем и выводим
                        formatted = self.format_log_line(log_data)
                        self.stdout.write(formatted)
                    else:
                        # Если не удалось распарсить, выводим как есть
                        self.stdout.write(line)
                    
                    self.stdout.flush()
                except Empty:
                    # Проверяем, не завершился ли процесс
                    if process.poll() is not None:
                        # Процесс завершился, читаем оставшиеся строки
                        while True:
                            try:
                                line = output_queue.get_nowait()
                                if line is None:
                                    break
                                log_data = self.parse_ollama_log(line)
                                if log_data:
                                    formatted = self.format_log_line(log_data)
                                    self.stdout.write(formatted)
                                else:
                                    self.stdout.write(line)
                            except Empty:
                                break
                        break
                    continue
            
            # Ждем завершения потока
            output_thread.join(timeout=1)
            
            # Ждем завершения процесса
            return_code = process.wait()
            
            if return_code != 0:
                self.stdout.write(self.style.ERROR(f'\n❌ Ollama завершился с кодом: {return_code}\n'))
                sys.exit(return_code)
            
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING('\n\n⚠️  Получен сигнал прерывания, завершение работы...\n'))
            try:
                if 'process' in locals() and process is not None:
                    process.terminate()
                    process.wait(timeout=5)
            except:
                pass
            logger.info('Получен сигнал прерывания, завершение работы')
            sys.exit(0)
        except FileNotFoundError:
            msg = 'Ollama не найден. Убедитесь, что Ollama установлен и доступен в PATH.'
            logger.error(msg)
            self.stdout.write(self.style.ERROR(f'\n❌ {msg}\n'))
            sys.exit(1)
        except Exception as e:
            logger.error(f'Ошибка при запуске Ollama: {e}')
            self.stdout.write(self.style.ERROR(f'\n❌ Ошибка: {e}\n'))
            try:
                if 'process' in locals() and process is not None:
                    process.terminate()
            except:
                pass
            raise
