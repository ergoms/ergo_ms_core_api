# Установка

## Зависимости

Добавлены в `pyproject.toml`:
- duckdb>=0.9.0
- sqlparse>=0.4.4
- llama-index-llms-ollama>=0.1.0

## Установка через систему команд

```bash
# Windows
ergoms python-install

# Или вручную
cd core/api
poetry install
```

## Ollama

1. Установка: https://ollama.ai/download
2. Загрузить модель: `ollama pull mistral`
3. Запуск: `ollama serve`

## Проверка

```bash
# Windows (из корня проекта)
virtual_env\python\Scripts\python.exe core\api\src\manage.py check

# Должно пройти без ошибок после установки зависимостей
```

## Запуск

```bash
# Через команды системы
ergoms dev                  # API dev server
ergoms start-client         # Client dev server

# Ollama должен быть запущен отдельно
ollama serve
```

