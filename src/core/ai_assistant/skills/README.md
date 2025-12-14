# Система модульных навыков (Skills) для AI ассистента

Система навыков позволяет расширять возможности AI ассистента, добавляя новые функции, которые могут выполняться автоматически на основе запросов пользователей.

## Архитектура

```
User Query → LLM (с описанием навыков) → Парсинг вызова навыка → Выполнение навыка → Результат в ответе
```

## Структура папок и регистр

### Структура папок

```
core/api/src/core/ai_assistant/skills/
├── __init__.py              # Экспорт основных классов
├── base.py                  # Базовый класс BaseSkill
├── manager.py               # Менеджер навыков (SkillsManager)
├── registry.py              # Реестр для регистрации навыков
├── integration.py           # Интеграция с LLM
├── builtin/                 # Встроенные навыки (организованы по категориям)
│   ├── __init__.py          # Экспорт встроенных навыков
│   ├── math/                # Категория: математические вычисления
│   │   ├── __init__.py
│   │   └── math_skill.py     # MathSkill
│   └── document/            # Категория: работа с документами
│       ├── __init__.py
│       └── document_skill.py # DocumentSkill
├── test_skills.py           # Тесты навыков
├── README.md                 # Документация
├── EXAMPLES.md               # Примеры
└── TESTING.md                # Инструкции по тестированию
```

### Правила именования

- **Файлы навыков**: `snake_case` с суффиксом `_skill.py` (например: `math_skill.py`, `document_skill.py`)
- **Классы навыков**: `PascalCase` с суффиксом `Skill` (например: `MathSkill`, `DocumentSkill`)
- **Имена навыков**: `snake_case` (например: `math_calculator`, `create_document`)

### Регистр навыков

Навыки автоматически регистрируются при первом обращении к `get_skills_manager()`:

1. **Встроенные навыки** - автоматически обнаруживаются из `builtin/`
2. **Навыки модулей** - регистрируются через `SkillRegistry.register()`

## Базовый класс навыка

Все навыки наследуются от `BaseSkill` и должны реализовать:

- `name` - уникальное имя навыка (snake_case)
- `description` - описание для LLM (когда использовать)
- `parameters` - параметры в формате JSON Schema
- `execute()` - выполнение навыка

## Пример создания навыка

```python
from src.core.ai_assistant.skills import BaseSkill, SkillResult

class MyCustomSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "my_custom_skill"
    
    @property
    def description(self) -> str:
        return "Описание того, что делает навык и когда его использовать"
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "Описание параметра"
                }
            },
            "required": ["param1"]
        }
    
    def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        # Логика выполнения навыка
        try:
            result = do_something(parameters)
            return SkillResult(
                success=True,
                result=result,
                metadata={'additional': 'info'}
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=str(e)
            )
```

## Регистрация навыка

### Встроенные навыки

Встроенные навыки организованы по категориям в подпапках `builtin/<категория>/`.

**Структура:**
1. Создайте папку категории в `builtin/` (например: `math/`, `document/`, `file/`)
2. Поместите файл навыка с именем `*_skill.py` в папку категории
3. Создайте `__init__.py` в папке категории для экспорта навыка

**Пример:**

```python
# builtin/my_category/my_custom_skill.py
from ...base import BaseSkill, SkillResult

class MyCustomSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "my_custom_skill"
    
    # ... остальные методы
```

```python
# builtin/my_category/__init__.py
from .my_custom_skill import MyCustomSkill

__all__ = ['MyCustomSkill']
```

Навык будет автоматически обнаружен и зарегистрирован при первом обращении к менеджеру навыков (рекурсивный поиск всех файлов `*_skill.py`).

**Важно**: 
- Используйте относительные импорты (`...base` вместо `src.core.ai_assistant.skills.base`)
- Имя файла должно заканчиваться на `_skill.py`
- Экспортируйте класс в `__init__.py` категории

### Навыки модулей

В модуле создайте файл `ai_assistant/skills/your_skill.py` и зарегистрируйте его:

```python
from src.core.ai_assistant.skills import SkillRegistry
from .your_skill import YourSkill

# При инициализации модуля
SkillRegistry.register(YourSkill())
```

## Как работает система

1. **Регистрация навыков** - навыки автоматически обнаруживаются из `builtin/`
2. **Доступность для LLM** - все навыки всегда доступны в промпте (как в Claude)
3. **Function calling** - LLM сам анализирует запрос и выбирает подходящий навык
4. **Выполнение** - система парсит JSON из ответа LLM и выполняет навык
5. **Результат** - результат навыка комбинируется с ответом LLM

### Преимущества подхода как в Claude

- **Гибкость** - нет жестких правил, LLM сам решает когда использовать навык
- **Естественность** - понимает контекст и намерения пользователя
- **Расширяемость** - легко добавлять новые навыки без изменения логики
- **Интеллект** - модель может комбинировать навыки для сложных задач
4. **Выполнение**: Система парсит JSON, выполняет навык и включает результат в ответ

## Формат вызова навыка

LLM должен вернуть JSON в формате:

```json
{
  "tool": "имя_навыка",
  "parameters": {
    "param1": "value1",
    "param2": "value2"
  }
}
```

## Встроенные навыки

- **math_calculator** - математические вычисления
- **create_document** - создание документов Word

## Добавление новых навыков

1. Создайте класс, наследующийся от `BaseSkill`
2. Реализуйте все обязательные методы
3. Поместите файл в `skills/builtin/` или зарегистрируйте через `SkillRegistry`
4. Навык будет автоматически доступен AI ассистенту

## Контекст выполнения

При выполнении навыка передается контекст:

```python
context = {
    'user': request.user,  # Пользователь
    'session': session,    # Сессия чата
    'module': module,      # Модуль ('chat', 'docs', 'bi')
}
```

Используйте контекст для доступа к данным пользователя, сессии и т.д.

## Тестирование

### Через Django команду
```bash
api test_skills
```

### Через утилиту ergoms
```bash
ergoms test_skills
```

### Ручное тестирование
```python
from src.core.ai_assistant.skills import get_skills_manager

manager = get_skills_manager()
skills = manager.get_all_skills()
print(f"Зарегистрировано навыков: {len(skills)}")

# Тестирование навыка
result = manager.execute_skill('math_calculator', "2+2", parameters={'expression': '2+2'})
print(result.success, result.result)
```

