# Тестирование навыков AI ассистента

## Способ 1: Через Django management команду (рекомендуется)

Самый простой способ - использовать готовую команду:

```bash
api test_skills
```

Или через утилиту ergoms:

```bash
ergoms test_skills
```

Эта команда автоматически проверит:
- Регистрацию всех навыков
- Определения функций для LLM
- Поиск подходящих навыков
- Выполнение навыков
- Парсинг вызовов навыков

## Способ 2: Через Python shell

Запустите Django shell и выполните скрипт:

```bash
api shell
```

Затем в shell:

```python
exec(open('src/core/ai_assistant/skills/test_skills.py').read())
```

**Важно:** Путь должен быть в кавычках!

Или вручную:

```python
from src.core.ai_assistant.skills import get_skills_manager

# Получаем менеджер
manager = get_skills_manager()

# Проверяем зарегистрированные навыки
skills = manager.get_all_skills()
for skill in skills:
    print(f"{skill.name}: {skill.description}")

# Проверяем поиск подходящих навыков
applicable = manager.find_applicable_skills("Посчитай 2+2")
print([s.name for s in applicable])

# Тестируем выполнение навыка
result = manager.execute_skill(
    'math_calculator',
    "Посчитай корень из 323982",
    parameters={'expression': 'sqrt(323982)'}
)
print(result.success, result.result)
```

## Способ 2: Через API (реальное использование)

### 2.1. Проверка через обычный чат

Отправьте POST запрос к `/api/ai_assistant/chat/`:

```bash
curl -X POST http://localhost:8000/api/ai_assistant/chat/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "Посчитай корень из 323982",
    "module": "general"
  }'
```

**Ожидаемое поведение:**
- LLM получает описание навыка `math_calculator` в промпте
- LLM должен вернуть JSON: `{"tool": "math_calculator", "parameters": {"expression": "sqrt(323982)"}}`
- Система парсит JSON, выполняет навык и возвращает результат

### 2.2. Проверка создания документа

```bash
curl -X POST http://localhost:8000/api/ai_assistant/chat/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "Создай документ с названием Тестовый документ и содержимым Это тестовый документ",
    "module": "general"
  }'
```

**Ожидаемое поведение:**
- LLM определяет, что нужен навык `create_document`
- LLM возвращает JSON с параметрами
- Система создает документ в базе знаний
- Возвращается сообщение об успешном создании

## Способ 3: Через веб-интерфейс

1. Откройте AI Assistant в браузере
2. Выберите модуль "General" (общий чат)
3. Отправьте запросы:
   - "Посчитай 2+2"
   - "Корень из 16"
   - "Создай документ с анализом данных"
   - "Найди производную x^2+2x+1"

**Что проверить:**
- Навык должен автоматически определиться и выполниться
- Результат должен быть точным (особенно для математики)
- В ответе не должно быть JSON кода вызова навыка

## Способ 4: Проверка логов

Проверьте логи Django для отладки:

```python
# В settings.py должен быть настроен логгер
import logging
logger = logging.getLogger('src.core.ai_assistant.skills')
logger.setLevel(logging.DEBUG)
```

В логах вы увидите:
- Регистрацию навыков при старте
- Поиск подходящих навыков для запроса
- Выполнение навыков
- Ошибки выполнения

## Отладка проблем

### Проблема: Навык не вызывается

1. **Проверьте регистрацию:**
   ```python
   manager = get_skills_manager()
   print(manager.get_all_skills())  # Должен показать навыки
   ```

2. **Проверьте промпт:**
   ```python
   from src.core.ai_assistant.skills.integration import build_skills_prompt
   skills = manager.get_function_definitions()
   prompt = build_skills_prompt(skills)
   print(prompt)  # Должен содержать описание навыков
   ```

3. **Проверьте ответ LLM:**
   - Включите логирование в `views.py`
   - Проверьте, что LLM получает описание навыков
   - Проверьте, что LLM возвращает JSON с вызовом навыка

### Проблема: LLM не возвращает JSON

- Убедитесь, что модель Ollama поддерживает function calling
- Попробуйте более явный промпт в `build_skills_prompt`
- Проверьте, что температура не слишком высокая (для точности JSON нужна низкая температура)

### Проблема: Навык выполняется, но результат неправильный

- Проверьте логи выполнения навыка
- Убедитесь, что параметры передаются корректно
- Проверьте метод `execute()` навыка

## Примеры тестовых запросов

### Математика:
- "Посчитай 2+2"
- "Корень из 323982"
- "Найди производную x^2"
- "Реши уравнение x^2-5x+6=0"
- "Упрости выражение (x+1)^2"

### Создание документов:
- "Создай документ с названием Отчет и содержимым Это отчет"
- "Создай Word документ с анализом"
- "Сформируй файл с информацией о проекте"

## Проверка интеграции с streaming

Для streaming запросов (`ChatStreamView`) проверка аналогична, но ответ приходит по частям через SSE.

```bash
curl -N -X POST http://localhost:8000/api/ai_assistant/chat/stream/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "message": "Посчитай корень из 323982",
    "module": "general"
  }'
```

В потоке должны быть события:
- `type: "chunk"` - части ответа
- `type: "skill_result"` - результат выполнения навыка (если есть)
- `type: "done"` - завершение

