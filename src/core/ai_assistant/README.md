# AI Assistant - BI Module

Модуль интеграции Fast BI для анализа табличных данных через естественный язык.

## Установка

```bash
# Установка зависимостей
ergoms python-install

# Или вручную
cd core/api
poetry install
```

Требования:
- Ollama (https://ollama.ai)
- Модель: `ollama pull mistral`

Подробнее: [INSTALL.md](./INSTALL.md)

## API

**GET** `/api/ai_assistant/files/` - Список файлов пользователя  
**POST** `/api/ai_assistant/bi_query/` - Запрос к данным  
**GET** `/api/ai_assistant/ollama_status/` - Статус Ollama

### Пример запроса

```json
POST /api/ai_assistant/bi_query/
{
  "file_id": 1,
  "question": "Средняя цена по категориям",
  "want_commentary": true
}
```

## Архитектура

```
User Query → FastBIService → DuckDB + Ollama → SQL Results
```

## Конфигурация

`fast_bi_service.py`:
```python
DEFAULT_MODEL = "mistral7b-tuned"  # Модель Ollama
MAX_OUTPUT_TOKENS = 256            # Максимум токенов в ответе
SQL_TIMEOUT_SEC = 30               # Таймаут SQL запроса
```

## Безопасность

- ✅ Только SELECT запросы (DML/DDL запрещены)
- ✅ Изоляция данных по пользователям  
- ✅ Защита от SQL injection
- ✅ Таймаут выполнения: 30 сек
- ✅ Работа только через Django API

## Требования

- **Ollama** - запущен и доступен
- **Модель** - загружена в Ollama (например `mistral`)
- **Python пакеты**: `duckdb`, `sqlparse`, `llama-index-llms-ollama`

## Troubleshooting

**ModuleNotFoundError: No module named 'duckdb':**
```bash
ergoms python-install
```

**Ollama недоступен:**
```bash
# Проверьте что Ollama запущен
ollama serve

# Проверьте доступность
curl http://localhost:11434/api/tags
```

**Модель не найдена:**
```bash
# Загрузите модель
ollama pull mistral

# Или другую модель
ollama pull mistral7b-tuned
```

**404 на /api/ai_assistant/files/:**
- Убедитесь что API запущен
- Проверьте что модуль зарегистрирован в INSTALLED_APPS
- Перезапустите API сервер
