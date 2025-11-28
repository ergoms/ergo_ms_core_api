"""
Django команда для управления моделями Ollama
"""

import subprocess
import sys
import psutil
import logging
import time
from pathlib import Path
from typing import Optional, List

from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from src.core.ollama_framework.methods import OllamaMethods

logger = logging.getLogger('core.ollama_framework.commands')


class Command(BaseCommand):
    help = 'Менеджер моделей Ollama'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ollama_methods = OllamaMethods(self.stdout)
    
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
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return None

    def start_ollama_background(self) -> bool:
        """
        Запускает Ollama сервер в фоновом режиме.

        Returns:
            bool: True если запуск успешен, False иначе
        """
        try:
            # Определяем путь к core/api/ (поднимаемся на 6 уровней вверх)
            # ollama.py -> commands -> management -> ollama_framework -> core -> src -> api
            api_dir = Path(__file__).resolve().parents[6]  # Путь к core/api/
            cmd: List[str] = ['ollama', 'serve']
            
            # Запускаем в фоне (на Windows и Linux по-разному)
            if sys.platform == 'win32':
                # Windows: используем CREATE_NO_WINDOW флаг
                process = subprocess.Popen(
                    cmd,
                    cwd=str(api_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
            else:
                # Linux: запускаем в фоне
                process = subprocess.Popen(
                    cmd,
                    cwd=str(api_dir),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            
            # Ждем немного, чтобы сервер успел запуститься
            time.sleep(2)
            
            # Проверяем, что процесс все еще работает
            if process.poll() is None:
                logger.info(f'Ollama запущен в фоне (PID: {process.pid})')
                return True
            else:
                logger.error('Ollama процесс завершился сразу после запуска')
                return False
                
        except FileNotFoundError:
            logger.error('Ollama не найден. Убедитесь, что Ollama установлен и доступен в PATH.')
            return False
        except Exception as e:
            logger.error(f'Ошибка при запуске Ollama: {e}')
            return False

    def ensure_ollama_running(self):
        """
        Убеждается, что Ollama сервер запущен. Если нет - запускает его.
        """
        if not self.find_ollama():
            self.stdout.write(self.style.WARNING('🦙 Ollama не запущен. Запускаю...\n'))  # type: ignore[attr-defined]
            
            if not self.start_ollama_background():
                raise CommandError('❌ Не удалось запустить Ollama. Убедитесь, что Ollama установлен и доступен в PATH.')
            
            # Ждем, пока Ollama станет доступен
            self.stdout.write(self.style.WARNING('⏳ Ожидание запуска Ollama...'))  # type: ignore[attr-defined]
            base_url = getattr(settings, 'OLLAMA_BASE_URL', 'http://localhost:11434')
            
            for i in range(30):
                try:
                    import httpx
                    response = httpx.get(f"{base_url}/api/tags", timeout=2.0)
                    if response.status_code == 200:
                        self.stdout.write(self.style.SUCCESS('\n✅ Ollama готов к работе\n'))  # type: ignore[attr-defined]
                        return
                except:
                    pass
                time.sleep(1)
                if (i + 1) % 5 == 0:
                    self.stdout.write(f'   ... еще {30 - i - 1} секунд')
            
            raise CommandError('❌ Ollama не стал доступен за отведенное время')
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--list',
            action='store_true',
            help='Показать список установленных моделей'
        )
        parser.add_argument(
            '--pull',
            type=str,
            help='Скачать модель (например: --pull mistral:latest)'
        )
        parser.add_argument(
            '--remove',
            type=str,
            help='Удалить модель (например: --remove mistral:latest)'
        )
        parser.add_argument(
            '--test',
            type=str,
            help='Протестировать модель (например: --test llama2:latest)'
        )
        parser.add_argument(
            '--info',
            action='store_true',
            help='Показать информацию о системе ollama'
        )

        parser.add_argument(
            '--train',
            type=str,
            help='Обучить модель на данных ERGO MS (например: --train llama2:latest)'
        )
        parser.add_argument(
            '--data',
            type=str,
            help='Путь к файлу данных в папке trained_models (например: --data training_data/ergo_navigation_data.jsonl)'
        )
        parser.add_argument(
            '--generate-data',
            action='store_true',
            help='Сгенерировать тренировочные данные для обучения'
        )
        
        # Аргументы для чата
        parser.add_argument(
            '--chat',
            nargs='+',
            help='Отправить сообщение к модели (например: --chat "Привет! Как дела?")'
        )
        parser.add_argument(
            '--prompt',
            nargs='+',
            help='Отправить запрос к модели (алиас для --chat, например: --prompt "Привет! Как дела?")'
        )
        parser.add_argument(
            '--model',
            type=str,
            default='llama2',
            help='Имя модели для использования (по умолчанию: llama2)'
        )
        parser.add_argument(
            '--interactive',
            action='store_true',
            help='Интерактивный режим для общения с моделью'
        )
        parser.add_argument(
            '--system-prompt',
            type=str,
            help='Системный промпт для модели'
        )
        parser.add_argument(
            '--temperature',
            type=float,
            default=0.7,
            help='Температура генерации (0.0-1.0, по умолчанию: 0.7)'
        )
        parser.add_argument(
            '--max-tokens',
            type=int,
            default=2048,
            help='Максимальное количество токенов в ответе (по умолчанию: 2048)'
        )
    
    def handle(self, *args, **options):
        list_models = options['list']
        pull_model = options['pull']
        remove_model = options['remove']
        test_model = options['test']
        show_info = options['info']
        train_model = options['train']
        data_file = options['data']
        generate_data = options['generate_data']
        
        # Новые аргументы для чата
        chat_message_parts = options['chat']
        prompt_message_parts = options.get('prompt')  # Поддержка --prompt
        model_name = options['model']
        interactive = options['interactive']
        system_prompt = options['system_prompt']
        temperature = options['temperature']
        max_tokens = options['max_tokens']
        
        # Объединяем части сообщения в одну строку (--prompt имеет приоритет над --chat)
        if prompt_message_parts:
            chat_message = ' '.join(prompt_message_parts)
        elif chat_message_parts:
            chat_message = ' '.join(chat_message_parts)
        else:
            chat_message = None
        
        try:
            # Для команд, требующих Ollama API, проверяем запуск сервера
            needs_ollama = bool(chat_message or interactive or test_model or train_model or generate_data)
            if needs_ollama:
                self.ensure_ollama_running()
            
            if show_info:
                self.ollama_methods.show_info()
            elif list_models:
                self.ollama_methods.list_models()
            elif pull_model:
                self.ollama_methods.pull_model(pull_model)
            elif remove_model:
                self.ollama_methods.remove_model(remove_model)
            elif test_model:
                self.ollama_methods.test_model(test_model)
            elif train_model:
                if not data_file:
                    self.stdout.write('❌ Укажите файл данных: --data путь/к/файлу.jsonl')
                    return
                self.ollama_methods.train_model(train_model, data_file)
            elif generate_data:
                self.ollama_methods.generate_training_data()
            elif chat_message:
                self._send_single_message(model_name, chat_message, system_prompt, temperature, max_tokens)
            elif interactive:
                self._run_interactive_mode(model_name, system_prompt, temperature, max_tokens)
            else:
                # Показать справку, если нет аргументов
                self.ollama_methods.show_help()
                
        except Exception as e:
            raise CommandError(f'Ошибка: {e}')
    
    def _send_single_message(self, model_name, message, system_prompt=None, temperature=0.7, max_tokens=2048):
        """Отправить одно сообщение к модели"""
        self.stdout.write(f'Отправляю сообщение к модели {model_name}...')
        self.stdout.write(f'Сообщение: {message}')
        self.stdout.write('-' * 50)
        
        answer = self.ollama_methods.send_message(model_name, message, system_prompt, temperature, max_tokens)
        
        if answer:
            self.stdout.write(f'Ответ: {answer}')
        else:
            self.stdout.write('Не удалось получить ответ от модели')
    
    def _run_interactive_mode(self, model_name, system_prompt=None, temperature=0.7, max_tokens=2048):
        """Запустить интерактивный режим"""
        # Проверяем доступность модели
        if not self.ollama_methods._check_model_availability(model_name):
            return
        
        self.stdout.write(f'Интерактивный режим с моделью {model_name}')
        self.stdout.write('Введите сообщения (Ctrl+C для выхода):')
        self.stdout.write('-' * 50)
        
        if system_prompt:
            self.stdout.write(f'Системный промпт: {system_prompt}')
            self.stdout.write('-' * 50)
        
        while True:
            try:
                # Получаем ввод пользователя
                user_input = input('\nВы: ').strip()
                
                if not user_input:
                    continue
                
                # Отправляем запрос
                self.stdout.write('\nМодель думает...')
                answer = self.ollama_methods.send_message(model_name, user_input, system_prompt, temperature, max_tokens)
                
                if answer:
                    self.stdout.write(f'Модель: {answer}')
                else:
                    self.stdout.write('Не удалось получить ответ от модели')
                
            except KeyboardInterrupt:
                self.stdout.write('\n\nДо свидания!')
                break
            except EOFError:
                self.stdout.write('\n\nДо свидания!')
                break
            except Exception as e:
                self.stdout.write(f'\nОшибка: {e}') 