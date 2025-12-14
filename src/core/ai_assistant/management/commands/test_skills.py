"""
Django management команда для тестирования навыков AI ассистента.

Использование:
    api test_skills
"""
import logging

from django.core.management.base import BaseCommand

from src.core.ai_assistant.skills import get_skills_manager
from src.core.ai_assistant.skills.integration import build_skills_prompt, execute_skill_from_llm_response, parse_skill_call_from_response

logger = logging.getLogger('core.ai_assistant.commands')


class Command(BaseCommand):
    """Команда для тестирования навыков AI ассистента."""
    
    help = 'Тестирование навыков AI ассистента'

    def handle(self, *args, **options):
        """Выполняет тестирование навыков."""
        self.stdout.write(self.style.SUCCESS("=" * 80))
        self.stdout.write(self.style.SUCCESS("ТЕСТИРОВАНИЕ НАВЫКОВ AI АССИСТЕНТА"))
        self.stdout.write(self.style.SUCCESS("=" * 80))

        # Получаем менеджер навыков
        manager = get_skills_manager()

        # 1. Проверка регистрации навыков
        self.stdout.write("\n1. ЗАРЕГИСТРИРОВАННЫЕ НАВЫКИ:")
        self.stdout.write("-" * 80)
        all_skills = manager.get_all_skills()
        if not all_skills:
            self.stdout.write(self.style.ERROR("❌ Навыки не найдены!"))
        else:
            for skill in all_skills:
                self.stdout.write(f"✓ {skill.name}: {skill.description[:100]}...")
        self.stdout.write(f"\nВсего навыков: {len(all_skills)}")

        # 2. Проверка определений функций для LLM
        self.stdout.write("\n2. ОПРЕДЕЛЕНИЯ ФУНКЦИЙ ДЛЯ LLM:")
        self.stdout.write("-" * 80)
        function_defs = manager.get_function_definitions()
        for func_def in function_defs:
            self.stdout.write(f"\n{func_def['name']}:")
            self.stdout.write(f"  Описание: {func_def['description'][:100]}...")
            params = func_def.get('parameters', {})
            if 'properties' in params:
                self.stdout.write(f"  Параметры: {list(params['properties'].keys())}")

        # 3. Проверка промпта с навыками
        self.stdout.write("\n3. ПРОМПТ С НАВЫКАМИ (первые 500 символов):")
        self.stdout.write("-" * 80)
        skills_prompt = build_skills_prompt(function_defs)
        preview = skills_prompt[:500] + "..." if len(skills_prompt) > 500 else skills_prompt
        self.stdout.write(preview)

        # 4. Информация о навыках
        self.stdout.write("\n4. ВСЕ НАВЫКИ ДОСТУПНЫ LLM:")
        self.stdout.write("-" * 80)
        self.stdout.write("Все навыки всегда доступны LLM, который сам выбирает подходящие")
        self.stdout.write("LLM анализирует запрос и описание навыков, чтобы решить, какой использовать")

        # 5. Тестирование выполнения навыков
        self.stdout.write("\n5. ВЫПОЛНЕНИЕ НАВЫКОВ:")
        self.stdout.write("-" * 80)

        # Тест MathSkill
        self.stdout.write("\nТест MathSkill:")
        math_skill = manager.get_skill('math_calculator')
        if math_skill:
            result = math_skill.execute(
                "Посчитай корень из 323982",
                parameters={'expression': 'sqrt(323982)'}
            )
            self.stdout.write(f"  Запрос: 'Посчитай корень из 323982'")
            if result.success:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Успех: {result.success}"))
                self.stdout.write(f"  Результат: {result.result[:200]}...")
            else:
                self.stdout.write(self.style.ERROR(f"  ✗ Ошибка: {result.error}"))
        else:
            self.stdout.write(self.style.ERROR("  ❌ MathSkill не найден!"))

        # Тест DocumentSkill
        self.stdout.write("\nТест DocumentSkill:")
        doc_skill = manager.get_skill('create_document')
        if doc_skill:
            self.stdout.write(self.style.SUCCESS("  ✓ Навык найден и зарегистрирован"))
            self.stdout.write("  ℹ️  Полное тестирование требует пользователя и базы данных")
            self.stdout.write("  ℹ️  Навык будет доступен LLM через function calling")
        else:
            self.stdout.write(self.style.ERROR("  ❌ DocumentSkill не найден!"))

        # 6. Тестирование парсинга вызова навыка из ответа LLM
        self.stdout.write("\n6. ПАРСИНГ ВЫЗОВА НАВЫКА ИЗ ОТВЕТА LLM:")
        self.stdout.write("-" * 80)
        test_responses = [
            '{"tool": "math_calculator", "parameters": {"expression": "2+2"}}',
            'Вот результат: ```json\n{"tool": "create_document", "parameters": {"title": "Тест", "content": "Содержимое"}}\n```',
            'Обычный ответ без навыка',
        ]
        for response in test_responses:
            skill_call = parse_skill_call_from_response(response)
            if skill_call:
                self.stdout.write(self.style.SUCCESS(f"  ✓ Найден вызов: {skill_call}"))
            else:
                self.stdout.write(f"  Вызов не найден")

        self.stdout.write("\n" + "=" * 80)
        self.stdout.write(self.style.SUCCESS("ТЕСТИРОВАНИЕ ЗАВЕРШЕНО"))
        self.stdout.write("=" * 80)

