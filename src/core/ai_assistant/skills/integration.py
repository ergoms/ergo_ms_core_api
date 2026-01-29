"""
Интеграция навыков с LLM через function calling.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from .manager import get_skills_manager
from .base import SkillResult

logger = logging.getLogger(__name__)


def build_skills_prompt(available_skills: List[Dict[str, Any]]) -> str:
    """
    Строит промпт с описанием доступных навыков для LLM.
    
    Args:
        available_skills: Список определений функций навыков
    
    Returns:
        Текст промпта с описанием навыков
    """
    if not available_skills:
        return ""
    
    prompt_parts = [
        "\n\n[ДОСТУПНЫЕ НАВЫКИ]",
        "У тебя есть доступ к следующим навыкам (tools).",
        "",
        "КРИТИЧЕСКИ ВАЖНО: Используй навыки ТОЛЬКО когда пользователь ЯВНО просит выполнить действие:",
        "- Вычисления: 'посчитай', 'вычисли', 'сколько будет'",
        "- Документы: 'создай документ', 'сделай файл', 'сформируй отчёт', 'выгрузи в файл'",
        "- Графики: 'построй график', 'создай график', 'визуализируй данные', 'нарисуй график'",
        "",
        "НЕ используй навыки если:",
        "- Пользователь задает вопрос или просит объяснить что-то",
        "- В ответе упоминается слово 'документ' в контексте информации (это НЕ запрос на создание)",
        "- Пользователь просит найти информацию или проиндексировать документ",
        "- Это обычный вопрос к базе знаний (RAG) - просто отвечай на основе контекста",
        "",
        "Для вопросов 'что такое?', 'расскажи', 'объясни', 'найди информацию' — просто отвечай без навыков.",
        ""
    ]
    
    for skill_def in available_skills:
        name = skill_def.get('name', '')
        description = skill_def.get('description', '')
        parameters = skill_def.get('parameters', {})
        props = parameters.get('properties', {})
        required = parameters.get('required', [])
        
        prompt_parts.append(f"**{name}**: {description}")
        
        if props:
            prompt_parts.append("  Параметры:")
            for param_name, param_info in props.items():
                param_desc = param_info.get('description', '')
                param_type = param_info.get('type', 'string')
                is_required = param_name in required
                req_mark = " (обязательный)" if is_required else " (опциональный)"
                prompt_parts.append(f"    - {param_name} ({param_type}): {param_desc}{req_mark}")
        
        prompt_parts.append("")
    
    prompt_parts.extend([
        "Чтобы ВЫПОЛНИТЬ навык, напиши ТОЧНО в таком формате:",
        '[EXECUTE]{"tool": "имя_навыка", "parameters": {"param1": "value1"}}',
        "",
        "ВАЖНО: Маркер [EXECUTE] обязателен! Без него навык не выполнится.",
        "Если навык не нужен — просто отвечай без [EXECUTE] и JSON.",
        "[/ДОСТУПНЫЕ НАВЫКИ]"
    ])
    
    return "\n".join(prompt_parts)


def _is_valid_tool_name(tool_name: str) -> bool:
    """Проверяет, что имя инструмента валидно (не none, null и т.п.)."""
    if not tool_name:
        return False
    invalid_names = {'none', 'null', 'n/a', 'na', '', 'нет', 'никакой'}
    return tool_name.lower().strip() not in invalid_names


def parse_skill_call_from_response(response: str) -> Optional[Dict[str, Any]]:
    """
    Парсит вызов навыка из ответа LLM.
    
    Ищет маркер [EXECUTE] с JSON в формате:
    [EXECUTE]{"tool": "skill_name", "parameters": {...}}
    
    Args:
        response: Ответ от LLM
    
    Returns:
        Словарь с именем навыка и параметрами, или None если вызов не найден
    """
    import re
    
    # Ищем маркер [EXECUTE]
    match = re.search(r'\[EXECUTE\]', response, re.IGNORECASE)
    if not match:
        return None
    
    # Находим JSON после [EXECUTE]
    json_start = response.find('{', match.end())
    if json_start == -1:
        return None
    
    # Находим конец JSON (с учётом вложенных скобок)
    brace_count = 0
    json_end = json_start
    for i in range(json_start, len(response)):
        if response[i] == '{':
            brace_count += 1
        elif response[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break
    
    if json_end <= json_start:
        return None
    
    json_str = response[json_start:json_end]
    
    try:
        data = json.loads(json_str)
        
        if 'tool' in data:
            tool_name = data['tool']
            if _is_valid_tool_name(tool_name):
                return {
                    'tool': tool_name,
                    'parameters': data.get('parameters', {})
                }
    except json.JSONDecodeError:
        pass
    
    return None


def execute_skill_from_llm_response(
    response: str,
    original_query: str,
    context: Optional[Dict[str, Any]] = None
) -> tuple[Optional[SkillResult], str, Optional[str], Optional[Dict[str, Any]]]:
    """
    Выполняет навык на основе ответа LLM.
    
    Args:
        response: Ответ от LLM
        original_query: Исходный запрос пользователя
        context: Дополнительный контекст
    
    Returns:
        Кортеж (SkillResult или None, очищенный ответ без JSON, display_name навыка или None, skill_call или None)
    """
    skill_call = parse_skill_call_from_response(response)
    
    if not skill_call:
        # Нет вызова навыка, возвращаем исходный ответ
        return None, response, None, None
    
    skill_name = skill_call.get('tool')
    parameters = skill_call.get('parameters', {})
    
    if not skill_name:
        return None, response, None, None
    
    manager = get_skills_manager()
    
    # Получаем display_name навыка
    skill = manager.get_skill(skill_name)
    skill_display_name = skill.display_name if skill else None
    
    skill_result = manager.execute_skill(skill_name, original_query, parameters, context)
    
    # Удаляем JSON из ответа (находим и удаляем весь JSON блок с вложенными скобками)
    cleaned_response = _remove_json_from_response(response)
    
    return skill_result, cleaned_response, skill_display_name, skill_call


def _remove_json_from_response(response: str) -> str:
    """
    Удаляет [EXECUTE]{...} вызова навыка из ответа LLM.
    """
    import re
    
    # Находим [EXECUTE] (регистронезависимо)
    match = re.search(r'\[EXECUTE\]', response, re.IGNORECASE)
    if not match:
        return response.strip()
    
    execute_start = match.start()
    execute_end = match.end()
    
    # Находим JSON после [EXECUTE]
    json_start = response.find('{', execute_end)
    if json_start == -1:
        # Удаляем только [EXECUTE]
        cleaned = response[:execute_start] + response[execute_end:]
        return cleaned.strip()
    
    # Находим конец JSON (с учётом вложенных скобок)
    brace_count = 0
    json_end = json_start
    for i in range(json_start, len(response)):
        if response[i] == '{':
            brace_count += 1
        elif response[i] == '}':
            brace_count -= 1
            if brace_count == 0:
                json_end = i + 1
                break
    
    # Удаляем [EXECUTE] вместе с JSON
    cleaned = response[:execute_start] + response[json_end:]
    return cleaned.strip()

