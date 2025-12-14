"""
Скрипт для тестирования навыков AI ассистента.

Использование в Django shell:
    python manage.py shell
    >>> exec(open('src/core/ai_assistant/skills/test_skills.py').read())
    
Или через Django management команду:
    api test_skills
"""
import os
import sys
from pathlib import Path

# Определяем путь к скрипту
_script_dir = Path(__file__).parent
_base_dir = _script_dir.parent.parent.parent.parent  # core/api/src
_src_dir = _base_dir / 'src'

# Добавляем путь к src в sys.path если его там нет
if str(_src_dir) not in sys.path:
    sys.path.insert(0, str(_src_dir))

import django

# Настройка Django окружения
if 'DJANGO_SETTINGS_MODULE' not in os.environ:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
    django.setup()

from src.core.ai_assistant.skills import get_skills_manager
from src.core.ai_assistant.skills.integration import build_skills_prompt, execute_skill_from_llm_response

print("=" * 80)
print("ТЕСТИРОВАНИЕ НАВЫКОВ AI АССИСТЕНТА")
print("=" * 80)

# Получаем менеджер навыков
manager = get_skills_manager()

# 1. Проверка регистрации навыков
print("\n1. ЗАРЕГИСТРИРОВАННЫЕ НАВЫКИ:")
print("-" * 80)
all_skills = manager.get_all_skills()
if not all_skills:
    print("❌ Навыки не найдены!")
else:
    for skill in all_skills:
        print(f"✓ {skill.name}: {skill.description[:100]}...")
print(f"\nВсего навыков: {len(all_skills)}")

# 2. Проверка определений функций для LLM
print("\n2. ОПРЕДЕЛЕНИЯ ФУНКЦИЙ ДЛЯ LLM:")
print("-" * 80)
function_defs = manager.get_function_definitions()
for func_def in function_defs:
    print(f"\n{func_def['name']}:")
    print(f"  Описание: {func_def['description'][:100]}...")
    params = func_def.get('parameters', {})
    if 'properties' in params:
        print(f"  Параметры: {list(params['properties'].keys())}")

# 3. Проверка промпта с навыками
print("\n3. ПРОМПТ С НАВЫКАМИ:")
print("-" * 80)
skills_prompt = build_skills_prompt(function_defs)
print(skills_prompt[:500] + "..." if len(skills_prompt) > 500 else skills_prompt)

# 4. Информация о навыках
print("\n4. ВСЕ НАВЫКИ ДОСТУПНЫ LLM:")
print("-" * 80)
print("Все навыки всегда доступны LLM, который сам выбирает подходящие")
print("LLM анализирует запрос и описание навыков, чтобы решить, какой использовать")

# 5. Тестирование выполнения навыков
print("\n5. ВЫПОЛНЕНИЕ НАВЫКОВ:")
print("-" * 80)

# Тест MathSkill
print("\nТест MathSkill:")
math_skill = manager.get_skill('math_calculator')
if math_skill:
    result = math_skill.execute(
        "Посчитай корень из 323982",
        parameters={'expression': 'sqrt(323982)'}
    )
    print(f"  Запрос: 'Посчитай корень из 323982'")
    print(f"  Успех: {result.success}")
    if result.success:
        print(f"  Результат: {result.result[:200]}...")
    else:
        print(f"  Ошибка: {result.error}")
else:
    print("  ❌ MathSkill не найден!")

# Тест DocumentSkill
print("\nТест DocumentSkill:")
doc_skill = manager.get_skill('create_document')
if doc_skill:
    # Для теста нужен пользователь, пропустим
    print("  ⚠️  Требуется пользователь для выполнения")
    print(f"  Навык найден: {doc_skill.name}")
else:
    print("  ❌ DocumentSkill не найден!")

# 6. Тестирование парсинга вызова навыка из ответа LLM
print("\n6. ПАРСИНГ ВЫЗОВА НАВЫКА ИЗ ОТВЕТА LLM:")
print("-" * 80)
test_responses = [
    '{"tool": "math_calculator", "parameters": {"expression": "2+2"}}',
    'Вот результат: ```json\n{"tool": "create_document", "parameters": {"title": "Тест", "content": "Содержимое"}}\n```',
    'Обычный ответ без навыка',
]
for response in test_responses:
    from src.core.ai_assistant.skills.integration import parse_skill_call_from_response
    skill_call = parse_skill_call_from_response(response)
    if skill_call:
        print(f"  Найден вызов: {skill_call}")
    else:
        print(f"  Вызов не найден")

print("\n" + "=" * 80)
print("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО")
print("=" * 80)

