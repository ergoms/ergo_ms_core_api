# Модуль Ollama Framework

Модуль для работы с моделями Ollama в системе ERGO MS. Предоставляет функциональность для управления моделями и чата с ними.

## Возможности

### Управление моделями

- Скачивание моделей из репозитория Ollama
- Удаление моделей
- Просмотр списка установленных моделей
- Тестирование моделей
- Получение информации о системе Ollama

### Чат с моделями

- Отправка одиночных сообщений к моделям
- Интерактивный режим общения
- Настройка параметров генерации (температура, токены)
- Использование системных промптов

## Структура модуля

```
ollama_framework/
├── __init__.py
├── apps.py
├── methods.py              # Основные методы работы с Ollama
├── models.py
├── serializers.py
├── views.py
├── urls.py
├── tests.py
├── scripts.py
├── management/
│   └── commands/
│       ├── __init__.py
│       └── ollama.py      # Django команда для управления
└── migrations/
```

## Установка и настройка

### Требования

1. **Ollama CLI** - должен быть установлен и запущен
2. **Python клиент Ollama** - `pip install ollama`
3. **Django** - для работы команд

### Проверка установки

```bash
# Проверить статус Ollama
cmd ollama --info

# Проверить доступные модели
cmd ollama --list
```

## Использование

### Команда `cmd ollama`

Основная команда для работы с Ollama через Django.

#### Управление моделями

```bash
# Показать список моделей
cmd ollama --list

# Скачать модель
cmd ollama --pull llama2:latest
cmd ollama --pull mistral:latest
cmd ollama --pull qwen:4b

# Удалить модель
cmd ollama --remove llama2:latest

# Протестировать модель
cmd ollama --test llama2:latest

# Информация о системе
cmd ollama --info
```

#### Чат с моделями

```bash
# Простое сообщение
cmd ollama --chat "Привет! Как дела?"

# С указанием модели
cmd ollama --chat "Напиши код на Python" --model llama2

# С системным промптом
cmd ollama --chat "Объясни ООП" --system-prompt "Ты - преподаватель программирования"

# Настройка параметров
cmd ollama --chat "Напиши стихотворение" --temperature 0.9 --max-tokens 1000

# Интерактивный режим
cmd ollama --interactive --model llama2
cmd ollama --interactive --model llama2 --system-prompt "Ты - помощник по программированию"
```

### Параметры команды

#### Управление моделями

- `--list` - Показать список установленных моделей
- `--pull <model>` - Скачать модель
- `--remove <model>` - Удалить модель
- `--test <model>` - Протестировать модель
- `--info` - Показать информацию о системе

#### Чат с моделями

- `--chat <message>` - Отправить сообщение к модели
- `--model <name>` - Имя модели (по умолчанию: llama2)
- `--interactive` - Интерактивный режим
- `--system-prompt` - Системный промпт
- `--temperature` - Температура генерации (0.0-1.0, по умолчанию: 0.7)
- `--max-tokens` - Максимальное количество токенов (по умолчанию: 2048)

## API методы

### Класс `OllamaMethods`

Основной класс для работы с Ollama.

#### Методы управления моделями

```python
from src.core.ollama_framework.methods import OllamaMethods

ollama = OllamaMethods(stdout)

# Получить клиент Ollama
client = ollama.get_ollama_client()

# Показать информацию о системе
ollama.show_info()

# Список моделей
ollama.list_models()

# Скачать модель
ollama.pull_model("llama2:latest")

# Удалить модель
ollama.remove_model("llama2:latest")

# Протестировать модель
ollama.test_model("llama2:latest")
```

#### Методы чата

```python
# Отправить сообщение
response = ollama.send_message(
    model_name="llama2",
    message="Привет! Как дела?",
    system_prompt="Ты - помощник",
    temperature=0.7,
    max_tokens=2048
)

# Проверить доступность модели
is_available = ollama._check_model_availability("llama2")
```

## Примеры использования

### Базовые примеры

```bash
# 1. Проверить систему
cmd ollama --info

# 2. Скачать популярную модель
cmd ollama --pull llama2:latest

# 3. Протестировать модель
cmd ollama --test llama2:latest

# 4. Отправить простое сообщение
cmd ollama --chat "Привет! Как дела?"

# 5. Интерактивный режим
cmd ollama --interactive --model llama2
```

### Продвинутые примеры

```bash
# Программирование с системным промптом
cmd ollama --chat "Напиши функцию сортировки" \
  --system-prompt "Ты - опытный Python разработчик" \
  --model llama2

# Креативное письмо
cmd ollama --chat "Напиши стихотворение о программировании" \
  --temperature 0.9 \
  --max-tokens 500

# Анализ данных
cmd ollama --chat "Объясни концепцию машинного обучения" \
  --system-prompt "Ты - эксперт по анализу данных" \
  --temperature 0.3

# Интерактивный режим с высокой креативностью
cmd ollama --interactive \
  --model llama2 \
  --system-prompt "Ты - креативный писатель" \
  --temperature 0.8
```

## Конфигурация

### Настройка моделей по умолчанию

В файле `methods.py` можно изменить модель по умолчанию:

```python
# В команде ollama.py
parser.add_argument(
    '--model',
    type=str,
    default='llama2',  # Изменить здесь
    help='Имя модели для использования'
)
```

### Параметры генерации по умолчанию

```python
# Температура (креативность)
default_temperature = 0.7  # 0.0 - детерминированный, 1.0 - очень креативный

# Максимальное количество токенов
default_max_tokens = 2048  # Ограничивает длину ответа
```

## Устранение неполадок

### Ошибки подключения

```bash
# 1. Проверить статус Ollama
cmd ollama --info

# 2. Запустить Ollama сервер
ollama serve

# 3. Проверить доступные модели
cmd ollama --list
```

### Проблемы с моделями

```bash
# Модель не найдена
cmd ollama --list  # Проверить доступные модели
cmd ollama --pull <model_name>  # Скачать модель

# Ошибка при скачивании
# Проверить интернет-соединение и доступность репозитория
```

### Проблемы с Python клиентом

```bash
# Обновить клиент
pip install --upgrade ollama

# Проверить установку
python -c "import ollama; print('OK')"
```

### Ошибки в командах

```bash
# Проверить справку
cmd ollama

# Правильный синтаксис для сообщений с пробелами
cmd ollama --chat "Привет! Как дела?"  # В кавычках
```

## Разработка

### Добавление новых функций

1. **Добавить метод в `OllamaMethods`**:

```python
def new_function(self, param):
    """Описание функции"""
    try:
        # Реализация
        pass
    except Exception as e:
        self.stdout.write(f'Ошибка: {e}')
```

2. **Добавить аргумент в команду**:

```python
# В ollama.py
parser.add_argument(
    '--new-option',
    type=str,
    help='Описание опции'
)
```

3. **Обработать в методе `handle`**:

```python
# В методе handle
elif new_option:
    self.ollama_methods.new_function(new_option)
```

### Тестирование

```bash
# Тест базовой функциональности
cmd ollama --info
cmd ollama --list

# Тест чата
cmd ollama --chat "Тест" --model llama2

# Тест интерактивного режима
cmd ollama --interactive --model llama2
```

## Безопасность

### Рекомендации

1. **Ограничение доступа** - Используйте модели только из доверенных источников
2. **Мониторинг** - Следите за использованием ресурсов
3. **Обновления** - Регулярно обновляйте Ollama и Python клиент
4. **Логирование** - Включите логирование для отслеживания использования

### Ограничения

- Модели могут занимать значительное место на диске
- Генерация требует вычислительных ресурсов
- Некоторые модели могут работать медленно на слабом оборудовании

## Лицензия

Модуль является частью системы ERGO MS и подчиняется соответствующим лицензионным соглашениям.

## Поддержка

Для получения поддержки обратитесь к документации проекта или создайте issue в репозитории.
