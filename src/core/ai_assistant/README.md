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
User Query → FastBIService → DuckDB → Ollama (HTTP) → SQL + Insights
```

- Используется только локальный Ollama API (HTTP клиент)
- Конфигурация описана в `config.py` (`RuntimeLLMConfig`)
- Параметры можно переопределять через module-config (`ollama_config` в запросе)

### Ключевые параметры

```python
provider="auto"          # auto | ollama
model="mistral7b-tuned"  # модель по умолчанию
sql_tokens=256           # лимит токенов для генерации SQL
commentary_tokens=192    # лимит токенов для комментариев
compute_device="gpu"     # gpu / cpu (0 GPU = CPU)
request_timeout=120.0    # таймаут HTTP запроса к Ollama
concurrency_limit=8      # пул соединений HTTP клиента
base_url="http://localhost:11434"  # адрес Ollama
```

Пример `ollama_config`:

```json
{
  "base_url": "http://127.0.0.1:11434",
  "model": "mistral",
  "compute_device": "cpu",
  "sql_tokens": 200
}
```

## Безопасность

- ✅ Только SELECT запросы (DML/DDL запрещены)
- ✅ Изоляция данных по пользователям  
- ✅ Защита от SQL injection
- ✅ Таймаут выполнения: 30 сек
- ✅ Работа только через Django API

## Требования

- **DuckDB**, **pandas**, **sqlparse**
- **Ollama** с загруженной моделью (`ollama pull mistral`)

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
