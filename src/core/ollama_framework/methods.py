"""
Методы для работы с Ollama
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime

from django.conf import settings


class OllamaMethods:
    """Класс с методами для работы с Ollama"""
    
    def __init__(self, stdout):
        self.stdout = stdout
    
    def get_ollama_client(self):
        """Получить клиент Ollama"""
        try:
            import ollama
            return ollama
        except ImportError:
            raise ImportError("Возникла ошибка при импорте ollama")
    
    def show_info(self):
        """Показать информацию о системе ollama"""
        try:
            client = self.get_ollama_client()
            
            # Получаем информацию о версии
            result = subprocess.run(['ollama', '--version'], 
                                  capture_output=True, text=True, check=True)
            
            self.stdout.write('Информация о системе Ollama:')
            self.stdout.write(f'CLI версия: {result.stdout.strip()}')
            
            # Проверяем подключение к серверу
            try:
                models = client.list()
                self.stdout.write('Сервер: работает ✓')
                self.stdout.write(f'Установлено моделей: {len(models.get("models", []))}')
            except Exception as e:
                self.stdout.write(f'Сервер: недоступен ({e})')
            
            # Версия Python клиента
            try:
                from importlib.metadata import version
                client_version = version('ollama')
                self.stdout.write(f'Python клиент: {client_version}')
            except:
                self.stdout.write('Python клиент: установлен')
                
        except ImportError:
            self.stdout.write('Ollama Python client не установлен')
        except subprocess.CalledProcessError:
            self.stdout.write('Ollama CLI не найден в PATH')
        except Exception as e:
            self.stdout.write(f'Ошибка: {e}')

    def list_models(self):
        """Показать список доступных моделей"""
        try:
            client = self.get_ollama_client()
            
            models = client.list()
            models_list = models.get('models', [])
            
            if not models_list:
                self.stdout.write('Модели не найдены.')
                self.stdout.write('Для скачивания модели используйте: cmd ollama --pull <model_name>')
                self.stdout.write('Популярные модели: llama2, codellama, mistral, qwen')
                return
            
            self.stdout.write(f'Найдено моделей: {len(models_list)}')
            self.stdout.write('-' * 40)
            
            for i, model in enumerate(models_list, 1):
                # Безопасное извлечение имени модели
                if hasattr(model, 'model'):
                    name = model.model
                    size = getattr(model, 'size', None)
                elif isinstance(model, dict):
                    name = model.get('name', str(model))
                    size = model.get('size', None)
                else:
                    name = str(model)
                    size = None
                
                # Конвертируем размер в читаемый формат
                if isinstance(size, int):
                    if size > 1024**3:
                        size_str = f"{size / (1024**3):.1f} GB"
                    elif size > 1024**2:
                        size_str = f"{size / (1024**2):.1f} MB"
                    else:
                        size_str = f"{size} bytes"
                else:
                    size_str = "Unknown size"
                
                self.stdout.write(f'{i:2d}. {name} ({size_str})')
                    
        except ImportError:
            self.stdout.write('Ollama Python client не установлен')
        except Exception as e:
            self.stdout.write(f'Ошибка получения списка моделей: {e}')

    def pull_model(self, model_name):
        """Скачать модель"""
        try:
            client = self.get_ollama_client()
            
            self.stdout.write(f'Скачиваю модель {model_name}...')
            
            # Отслеживание прогресса (если возможно)
            client.pull(model_name)
            
            self.stdout.write(f'✓ Модель {model_name} успешно скачана')
            
        except ImportError:
            self.stdout.write('Ollama Python client не установлен')
        except Exception as e:
            self.stdout.write(f'Ошибка при скачивании модели: {e}')

    def remove_model(self, model_name):
        """Удалить модель"""
        try:
            client = self.get_ollama_client()
            
            # Проверяем что модель существует
            models = client.list()
            available_models = []
            for model in models.get('models', []):
                if hasattr(model, 'model'):
                    model_name_from_api = model.model
                elif isinstance(model, dict):
                    model_name_from_api = model.get('name', str(model))
                else:
                    model_name_from_api = str(model)
                available_models.append(model_name_from_api)
            
            if model_name not in available_models:
                self.stdout.write(f'Модель {model_name} не найдена')
                return
            
            # Удаляем модель
            client.delete(model_name)
            self.stdout.write(f'✓ Модель {model_name} удалена')
            
        except ImportError:
            self.stdout.write('Ollama Python client не установлен')
        except Exception as e:
            self.stdout.write(f'Ошибка при удалении модели: {e}')

    def show_help(self):
        """Показать справку по использованию"""
        self.stdout.write('Менеджер моделей Ollama')
        self.stdout.write('=' * 30)
        self.stdout.write('')
        self.stdout.write('Управление моделями:')
        self.stdout.write('  --list              Показать установленные модели')
        self.stdout.write('  --pull <model>      Скачать модель')
        self.stdout.write('  --remove <model>    Удалить модель')
        self.stdout.write('  --test <model>      Протестировать модель')
        self.stdout.write('  --info              Информация о системе')
        self.stdout.write('  --train <model>     Обучить модель на данных ERGO MS')
        self.stdout.write('  --data <file>       Путь к файлу данных в trained_models')
        self.stdout.write('')
        self.stdout.write('Чат с моделями:')
        self.stdout.write('  --chat <message>    Отправить сообщение к модели')
        self.stdout.write('  --model <name>      Имя модели (по умолчанию: llama2)')
        self.stdout.write('  --interactive       Интерактивный режим')
        self.stdout.write('  --system-prompt     Системный промпт')
        self.stdout.write('  --temperature       Температура генерации (0.0-1.0)')
        self.stdout.write('  --max-tokens        Максимальное количество токенов')
        self.stdout.write('')
        self.stdout.write('Примеры управления:')
        self.stdout.write('  cmd ollama --list')
        self.stdout.write('  cmd ollama --pull mistral:latest')
        self.stdout.write('  cmd ollama --test llama2:latest')
        self.stdout.write('  cmd ollama --train llama2:latest --data training_data/ergo_navigation_data.jsonl')
        self.stdout.write('')
        self.stdout.write('Примеры чата:')
        self.stdout.write('  cmd ollama --chat "Привет! Как дела?"')
        self.stdout.write('  cmd ollama --chat "Напиши код на Python" --model llama2')
        self.stdout.write('  cmd ollama --interactive --model llama2')
        self.stdout.write('  cmd ollama --chat "Объясни ООП" --system-prompt "Ты - преподаватель программирования"')
        self.stdout.write('  cmd ollama --chat "Напиши стихотворение" --temperature 0.9')
        self.stdout.write('')
        self.stdout.write('Примечание: Для сообщений с пробелами используйте кавычки:')
        self.stdout.write('  cmd ollama --chat "Привет! Как дела?"')
        self.stdout.write('  cmd ollama --chat "Напиши функцию на Python" --model llama2')

    def test_model(self, model_name):
        """Тестирование модели"""
        try:
            client = self.get_ollama_client()
            
            # Проверяем доступность модели
            models = client.list()
            available_models = []
            for model in models.get('models', []):
                if hasattr(model, 'model'):
                    model_name_from_api = model.model
                elif isinstance(model, dict):
                    model_name_from_api = model.get('name', str(model))
                else:
                    model_name_from_api = str(model)
                available_models.append(model_name_from_api)
            
            if model_name not in available_models:
                self.stdout.write(f'Модель {model_name} не найдена.')
                self.stdout.write(f'Доступные модели: {", ".join(available_models)}')
                return
            
            # Простой тест
            self.stdout.write(f'Тестирую модель {model_name}...')
            
            test_prompt = "Привет! Как дела?"
            
            response = client.chat(
                model=model_name,
                messages=[{"role": "user", "content": test_prompt}]
            )
            
            answer = response["message"]["content"]
            self.stdout.write(f'Запрос: {test_prompt}')
            self.stdout.write(f'Ответ: {answer}')
            self.stdout.write('✓ Модель работает корректно')
                
        except ImportError:
            self.stdout.write('Ollama Python client не установлен')
        except Exception as e:
            self.stdout.write(f'Ошибка при тестировании: {e}')
    
    def train_model(self, base_model, data_file_path):
        """Обучение модели на данных ERGO MS"""
        try:
            # Проверяем наличие базовой модели
            client = self.get_ollama_client()
            models = client.list()
            
            available_models = []
            for model in models.get('models', []):
                # API возвращает объекты Model с атрибутом model
                if hasattr(model, 'model'):
                    model_name = model.model
                elif isinstance(model, dict):
                    model_name = model.get('name', str(model))
                else:
                    model_name = str(model)
                available_models.append(model_name)
            
            if base_model not in available_models:
                self.stdout.write(f'❌ Базовая модель {base_model} не найдена')
                self.stdout.write(f'Доступные модели: {", ".join(available_models)}')
                return
            
            # Проверяем наличие файла данных (относительно trained_models)
            trained_models_dir = Path(settings.BASE_DIR).parent / 'trained_models'
            data_file = trained_models_dir / data_file_path
            
            if not data_file.exists():
                self.stdout.write(f'❌ Файл данных не найден: {data_file}')
                return
            
            # Создаем уникальное имя для обученной модели
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Извлекаем имя файла без расширения для имени модели
            file_stem = Path(data_file_path).stem
            trained_model_name = f"{file_stem}-{timestamp}"
            
            self.stdout.write(f'Начинаю обучение модели {trained_model_name}')
            self.stdout.write(f'Базовая модель: {base_model}')
            self.stdout.write(f'Файл данных: {data_file}')
            
            # Создаем Modelfile для fine-tuning
            modelfile_path = trained_models_dir / f'{trained_model_name}.modelfile'
            
            # Читаем JSONL и извлекаем примеры для системного промпта
            training_examples = []
            with open(data_file, 'r', encoding='utf-8') as jsonl_file:
                count = 0
                for line in jsonl_file:
                    if line.strip() and count < 20:  # Берем первые 20 примеров
                        data = json.loads(line)
                        messages = data.get('messages', [])
                        if len(messages) >= 2:
                            user_msg = messages[0].get('content', '')
                            assistant_msg = messages[1].get('content', '')
                            training_examples.append(f"Пример {count + 1}:\nПользователь: {user_msg}\nАссистент: {assistant_msg}")
                            count += 1
            
            examples_text = "\n\n".join(training_examples)
            
            modelfile_content = f"""FROM {base_model}

PARAMETER temperature 0.3
PARAMETER top_p 0.8
PARAMETER repeat_penalty 1.1

SYSTEM \"\"\"Вы - навигационный ассистент системы ERGO MS. 
Ваша задача - помогать пользователям перемещаться по различным разделам системы.

Основные модули системы:
- Личный кабинет (профиль, безопасность)
- CRM - управление клиентами
- LMS - система обучения  
- BI - бизнес-аналитика
- Мессенджер - внутренние сообщения
- Email - почтовая система
- Экспертная система
- Анализ активов
- Анализ города
- Аналитика образования
- Анализ пористости

ВАЖНО: Всегда отвечайте в точном JSON формате без дополнительного текста:
{{"routeName": "точное_название_маршрута", "confidence": 0.9, "reasoning": "краткое объяснение", "needsClarification": false}}

Примеры правильных ответов:

{examples_text}

Отвечайте только в указанном JSON формате!\"\"\"

TEMPLATE \"\"\"
{{{{ if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{ end }}}}{{{{ if .Prompt }}}}<|im_start|>user
{{{{ .Prompt }}}}<|im_end|>
{{{{ end }}}}<|im_start|>assistant
{{{{ .Response }}}}<|im_end|>
\"\"\"

PARAMETER stop "<|im_end|>"
PARAMETER stop "<|im_start|\""""
            
            # Записываем Modelfile
            with open(modelfile_path, 'w', encoding='utf-8') as f:
                f.write(modelfile_content)
            
            # Создаем модель через ollama
            result = subprocess.run([
                'ollama', 'create', trained_model_name, '-f', str(modelfile_path)
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                self.stdout.write(f'✓ Модель {trained_model_name} создана')
                
                # Сохраняем информацию о модели
                model_info_file = trained_models_dir / f'{trained_model_name}_info.txt'
                
                with open(model_info_file, 'w', encoding='utf-8') as f:
                    f.write(f"Обученная модель ERGO MS\n")
                    f.write(f"Создана: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                    f.write(f"Базовая модель: {base_model}\n")
                    f.write(f"Название: {trained_model_name}\n")
                    f.write(f"Данные: {data_file}\n")
                    f.write(f"Modelfile: {modelfile_path}\n")
                
            else:
                self.stdout.write(f'❌ Ошибка создания модели: {result.stderr}')
                
        except Exception as e:
            self.stdout.write(f'❌ Ошибка обучения: {e}')
    
    def send_message(self, model_name, message, system_prompt=None, temperature=0.7, max_tokens=2048):
        """Отправить сообщение к модели и получить ответ"""
        try:
            client = self.get_ollama_client()
            
            # Проверяем доступность модели
            if not self._check_model_availability(model_name):
                return None
            
            # Формируем сообщения
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": message})
            
            # Отправляем запрос
            response = client.chat(
                model=model_name,
                messages=messages,
                options={
                    'temperature': temperature,
                    'num_predict': max_tokens
                }
            )
            
            return response["message"]["content"]
            
        except Exception as e:
            self.stdout.write(f'Ошибка при отправке сообщения: {e}')
            return None
    
    def _check_model_availability(self, model_name):
        """Проверить доступность модели"""
        try:
            client = self.get_ollama_client()
            models = client.list()
            
            available_models = []
            for model in models.get('models', []):
                if hasattr(model, 'model'):
                    model_name_from_api = model.model
                elif isinstance(model, dict):
                    model_name_from_api = model.get('name', str(model))
                else:
                    model_name_from_api = str(model)
                available_models.append(model_name_from_api)
            
            if model_name not in available_models:
                self.stdout.write(f'❌ Модель {model_name} не найдена.')
                self.stdout.write(f'Доступные модели: {", ".join(available_models)}')
                self.stdout.write('Для скачивания модели используйте: cmd ollama --pull <model_name>')
                return False
            
            return True
            
        except Exception as e:
            self.stdout.write(f'Ошибка при проверке модели: {e}')
            return False