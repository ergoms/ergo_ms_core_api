# API документация Ollama Framework

Техническая документация для разработчиков, использующих модуль ollama_framework.

## Класс OllamaMethods

Основной класс для работы с Ollama API.

### Конструктор

```python
def __init__(self, stdout)
```

**Параметры:**

- `stdout` - объект для вывода сообщений

### Методы управления моделями

#### get_ollama_client()

Получить клиент Ollama.

```python
def get_ollama_client(self) -> ollama
```

**Возвращает:**

- Объект клиента Ollama

**Исключения:**

- `ImportError` - если модуль ollama не установлен

#### show_info()

Показать информацию о системе Ollama.

```python
def show_info(self) -> None
```

Выводит:

- Версию CLI Ollama
- Статус сервера
- Количество установленных моделей
- Версию Python клиента

#### list_models()

Показать список доступных моделей.

```python
def list_models(self) -> None
```

Выводит:

- Количество моделей
- Список моделей с размерами

#### pull_model(model_name)

Скачать модель.

```python
def pull_model(self, model_name: str) -> None
```

**Параметры:**

- `model_name` - имя модели для скачивания

#### remove_model(model_name)

Удалить модель.

```python
def remove_model(self, model_name: str) -> None
```

**Параметры:**

- `model_name` - имя модели для удаления

#### test_model(model_name)

Протестировать модель.

```python
def test_model(self, model_name: str) -> None
```

**Параметры:**

- `model_name` - имя модели для тестирования

### Методы чата

#### send_message(model_name, message, system_prompt=None, temperature=0.7, max_tokens=2048)

Отправить сообщение к модели и получить ответ.

```python
def send_message(
    self,
    model_name: str,
    message: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048
) -> Optional[str]
```

**Параметры:**

- `model_name` - имя модели
- `message` - сообщение пользователя
- `system_prompt` - системный промпт (опционально)
- `temperature` - температура генерации (0.0-1.0)
- `max_tokens` - максимальное количество токенов

**Возвращает:**

- Ответ модели или `None` при ошибке

#### \_check_model_availability(model_name)

Проверить доступность модели.

```python
def _check_model_availability(self, model_name: str) -> bool
```

**Параметры:**

- `model_name` - имя модели для проверки

**Возвращает:**

- `True` если модель доступна, `False` иначе

### Методы обучения

#### train_model(base_model, data_file_path)

Обучить модель на данных ERGO MS.

```python
def train_model(self, base_model: str, data_file_path: str) -> None
```

**Параметры:**

- `base_model` - базовая модель для обучения
- `data_file_path` - путь к файлу данных в формате JSONL

### Методы справки

#### show_help()

Показать справку по использованию.

```python
def show_help(self) -> None
```

## Команда Django

### Класс Command

Django команда для управления Ollama.

#### Конструктор

```python
def __init__(self, *args, **kwargs)
```

#### add_arguments(parser)

Добавить аргументы команды.

```python
def add_arguments(self, parser) -> None
```

**Аргументы управления моделями:**

- `--list` - показать список моделей
- `--pull <model>` - скачать модель
- `--remove <model>` - удалить модель
- `--test <model>` - протестировать модель
- `--info` - показать информацию о системе
- `--data <file>` - путь к файлу данных

**Аргументы чата:**

- `--chat <message>` - отправить сообщение
- `--model <name>` - имя модели
- `--interactive` - интерактивный режим
- `--system-prompt` - системный промпт
- `--temperature` - температура генерации
- `--max-tokens` - максимальное количество токенов

#### handle(\*args, \*\*options)

Обработать команду.

```python
def handle(self, *args, **options) -> None
```

#### \_send_single_message(model_name, message, system_prompt=None, temperature=0.7, max_tokens=2048)

Отправить одно сообщение к модели.

```python
def _send_single_message(
    self,
    model_name: str,
    message: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048
) -> None
```

#### \_run_interactive_mode(model_name, system_prompt=None, temperature=0.7, max_tokens=2048)

Запустить интерактивный режим.

```python
def _run_interactive_mode(
    self,
    model_name: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: int = 2048
) -> None
```

## Примеры использования API

### Базовое использование

```python
from src.core.ollama_framework.methods import OllamaMethods
from django.core.management.base import OutputWrapper
import sys

# Создание экземпляра
stdout = OutputWrapper(sys.stdout)
ollama = OllamaMethods(stdout)

# Получение клиента
client = ollama.get_ollama_client()

# Показать информацию
ollama.show_info()

# Список моделей
ollama.list_models()
```

### Работа с чатом

```python
# Отправить сообщение
response = ollama.send_message(
    model_name="llama2",
    message="Привет! Как дела?",
    system_prompt="Ты - помощник",
    temperature=0.7,
    max_tokens=2048
)

if response:
    print(f"Ответ: {response}")
else:
    print("Не удалось получить ответ")

# Проверить доступность модели
if ollama._check_model_availability("llama2"):
    print("Модель доступна")
else:
    print("Модель недоступна")
```

### Управление моделями

```python
# Скачать модель
ollama.pull_model("llama2:latest")

# Удалить модель
ollama.remove_model("llama2:latest")

```

## Расширение функциональности

### Добавление нового метода

```python
class OllamaMethods:
    def new_method(self, param: str) -> None:
        """Описание нового метода"""
        try:
            client = self.get_ollama_client()

            # Реализация метода
            result = client.some_operation(param)

            self.stdout.write(f"Результат: {result}")

        except Exception as e:
            self.stdout.write(f"Ошибка: {e}")
```

### Добавление новой команды

```python
# В add_arguments
parser.add_argument(
    '--new-option',
    type=str,
    help='Описание новой опции'
)

# В handle
elif options['new_option']:
    self.ollama_methods.new_method(options['new_option'])
```

## Обработка ошибок

### Типичные исключения

```python
try:
    client = ollama.get_ollama_client()
except ImportError:
    print("Ollama Python client не установлен")

try:
    response = ollama.send_message("llama2", "Привет")
except Exception as e:
    print(f"Ошибка при отправке сообщения: {e}")
```

### Проверка доступности

```python
# Проверить модель перед использованием
if not ollama._check_model_availability("llama2"):
    print("Модель llama2 недоступна")
    return

# Безопасная отправка сообщения
response = ollama.send_message("llama2", "Привет")
if response is None:
    print("Не удалось получить ответ")
```

## Конфигурация

### Настройка параметров по умолчанию

```python
# В конструкторе или методе
DEFAULT_TEMPERATURE = 0.7
DEFAULT_MAX_TOKENS = 2048
DEFAULT_MODEL = "llama2"

# Использование
response = ollama.send_message(
    model_name=DEFAULT_MODEL,
    message="Привет",
    temperature=DEFAULT_TEMPERATURE,
    max_tokens=DEFAULT_MAX_TOKENS
)
```

### Логирование

```python
import logging

logger = logging.getLogger(__name__)

class OllamaMethods:
    def send_message(self, model_name: str, message: str, **kwargs):
        try:
            logger.info(f"Отправка сообщения к модели {model_name}")
            # Реализация
            logger.info("Сообщение отправлено успешно")
        except Exception as e:
            logger.error(f"Ошибка при отправке сообщения: {e}")
            raise
```

## Производительность

### Оптимизация запросов

```python
# Кэширование клиента
class OllamaMethods:
    def __init__(self, stdout):
        self.stdout = stdout
        self._client = None

    def get_ollama_client(self):
        if self._client is None:
            self._client = ollama
        return self._client
```

### Мониторинг ресурсов

```python
import time
import psutil

def monitor_performance(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss

        result = func(*args, **kwargs)

        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss

        print(f"Время выполнения: {end_time - start_time:.2f}с")
        print(f"Использование памяти: {(end_memory - start_memory) / 1024 / 1024:.2f}MB")

        return result
    return wrapper

# Использование
@monitor_performance
def send_message_with_monitoring(self, model_name, message):
    return self.send_message(model_name, message)
```

## Безопасность

### Валидация входных данных

```python
def validate_model_name(model_name: str) -> bool:
    """Валидация имени модели"""
    import re
    pattern = r'^[a-zA-Z0-9:_-]+$'
    return bool(re.match(pattern, model_name))

def send_message_safe(self, model_name: str, message: str, **kwargs):
    """Безопасная отправка сообщения"""
    if not validate_model_name(model_name):
        raise ValueError(f"Недопустимое имя модели: {model_name}")

    if len(message) > 10000:
        raise ValueError("Сообщение слишком длинное")

    return self.send_message(model_name, message, **kwargs)
```

### Ограничение доступа

```python
ALLOWED_MODELS = {"llama2", "mistral", "codellama"}

def is_model_allowed(model_name: str) -> bool:
    """Проверить, разрешена ли модель"""
    return model_name in ALLOWED_MODELS

def send_message_restricted(self, model_name: str, message: str, **kwargs):
    """Отправка сообщения с ограничениями"""
    if not is_model_allowed(model_name):
        raise ValueError(f"Модель {model_name} не разрешена")

    return self.send_message(model_name, message, **kwargs)
```
