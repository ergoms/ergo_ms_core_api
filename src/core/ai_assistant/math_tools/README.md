# Математические инструменты AI Ассистента

Модуль для выполнения математических вычислений в чате AI ассистента с использованием SymPy.

## Возможности

### Поддерживаемые операции

| Операция | Примеры запросов |
|----------|-----------------|
| **Арифметика** | `посчитай 2+2*3`, `сколько будет 15/3` |
| **Производные** | `производная x^2`, `найди производную sin(x)` |
| **Интегралы** | `интеграл x^2 dx`, `проинтегрировать cos(x)` |
| **Пределы** | `предел при x->0 sin(x)/x` |
| **Уравнения** | `реши x^2 - 4 = 0`, `найди корни x^2 + 2x + 1` |
| **Упрощение** | `упрости (x+1)^2 - x^2` |
| **Раскрытие** | `раскрой (a+b)^3` |
| **Факторизация** | `разложи на множители x^2 - 1` |
| **Статистика** | `среднее от 1, 2, 3, 4, 5` |

### Поддерживаемые функции

```
sqrt, sin, cos, tan, asin, acos, atan
sinh, cosh, tanh, exp, log, log10, log2
floor, ceil, factorial, gcd, lcm
degrees, radians, abs, round, min, max
```

### Константы

```
pi, e, inf, tau
```

## Архитектура

```
User Message → MathExpressionParser → MathOperationType
                                           ↓
                                    MathToolsService
                                    ↓              ↓
                           SafeMathExecutor   SymPy (символьная)
                           (NumPy, численная)
                                           ↓
                                      MathResult → Chat Response
```

## Использование в коде

```python
from src.core.ai_assistant.math_tools import MathToolsService

service = MathToolsService()

# Проверка математического запроса
if service.is_math_query("посчитай 2+2"):
    result = service.calculate("посчитай 2+2")
    if result.success:
        print(result.result)  # 4
        print(result.result_pretty)  # "4"

# Символьные вычисления
result = service.calculate("производная x^3")
print(result.result_latex)  # "3x^2"
print(result.steps)  # Шаги решения

# Решение уравнений
result = service.calculate("реши x^2 - 4 = 0")
print(result.result)  # [-2, 2]
```

## Компоненты

### MathExpressionParser

Парсер для распознавания типа математической операции из текста на естественном языке.

```python
from src.core.ai_assistant.math_tools import MathExpressionParser

parser = MathExpressionParser()
parsed = parser.parse("найди производную x^2 + 2x")
print(parsed.operation_type)  # MathOperationType.CALCULUS_DERIVATIVE
print(parsed.expression)  # "x**2 + 2*x"
print(parsed.variables)  # {"variable": "x"}
```

### SafeMathExecutor

Безопасный исполнитель для численных вычислений (без eval/exec).

```python
from src.core.ai_assistant.math_tools import SafeMathExecutor

executor = SafeMathExecutor()
result = executor.evaluate("2 + 3 * sin(pi/2)")  # 5.0
result = executor.evaluate("x^2 + y", {"x": 3, "y": 1})  # 10
```

### MathToolsService

Главный сервис, объединяющий парсер и исполнители.

## Зависимости

- **SymPy** - символьная математика
- **NumPy** - численные вычисления (уже в проекте)

## Установка

```bash
ergoms python-install
```

## Интеграция с чатом

Математические вычисления автоматически интегрированы в ChatView и ChatStreamView:

1. При получении сообщения проверяется, является ли оно математическим запросом
2. Если да - выполняется вычисление через MathToolsService
3. Результат добавляется в контекст для LLM
4. LLM комментирует результат

### Пример ответа в чате

```
📈 Производная

**Шаги решения:**
1. Исходное выражение: x²
2. Берём производную по x
3. Результат: 2x

**Результат:**
```
2*x
```

---

Производная функции x² равна 2x. Это означает, что скорость изменения функции
в любой точке x равна удвоенному значению этой точки.
```

## Безопасность

- Используется AST парсинг вместо eval/exec
- Белый список операторов и функций
- Ограничение на типы узлов AST
- Защита от инъекций кода

