"""
Django команда для управления моделями Ollama
"""

from django.core.management.base import BaseCommand, CommandError
from src.core.ollama_framework.methods import OllamaMethods


class Command(BaseCommand):
    help = 'Менеджер моделей Ollama'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ollama_methods = OllamaMethods(self.stdout)
    
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
        model_name = options['model']
        interactive = options['interactive']
        system_prompt = options['system_prompt']
        temperature = options['temperature']
        max_tokens = options['max_tokens']
        
        # Объединяем части сообщения в одну строку
        chat_message = ' '.join(chat_message_parts) if chat_message_parts else None
        
        try:
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