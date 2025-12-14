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
        "У тебя есть доступ к следующим навыкам (tools), которые ты можешь использовать:",
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
        "Чтобы использовать навык, ответь в формате JSON:",
        '{"tool": "имя_навыка", "parameters": {"param1": "value1", "param2": "value2"}}',
        "",
        "Если навык не нужен, просто ответь обычным текстом.",
        "[/ДОСТУПНЫЕ НАВЫКИ]"
    ])
    
    return "\n".join(prompt_parts)


def parse_skill_call_from_response(response: str) -> Optional[Dict[str, Any]]:
    """
    Парсит вызов навыка из ответа LLM.
    
    Ищет JSON в формате:
    {"tool": "skill_name", "parameters": {...}}
    
    Args:
        response: Ответ от LLM
    
    Returns:
        Словарь с именем навыка и параметрами, или None если вызов не найден
    """
    # Ищем JSON блок в ответе
    json_patterns = [
        r'\{[^{}]*"tool"[^{}]*\}',  # Простой JSON
        r'```json\s*(\{.*?\})\s*```',  # JSON в блоке кода
        r'```\s*(\{.*?\})\s*```',  # JSON в блоке без указания языка
    ]
    
    for pattern in json_patterns:
        import re
        matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
        for match in matches:
            json_str = match if isinstance(match, str) else match
            try:
                data = json.loads(json_str)
                if 'tool' in data and 'parameters' in data:
                    return {
                        'tool': data['tool'],
                        'parameters': data.get('parameters', {})
                    }
            except json.JSONDecodeError:
                continue
    
    # Пытаемся найти JSON в любом месте ответа
    try:
        # Ищем первый валидный JSON объект
        start_idx = response.find('{')
        if start_idx != -1:
            # Находим закрывающую скобку
            brace_count = 0
            end_idx = start_idx
            for i in range(start_idx, len(response)):
                if response[i] == '{':
                    brace_count += 1
                elif response[i] == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i + 1
                        break
            
            if end_idx > start_idx:
                json_str = response[start_idx:end_idx]
                data = json.loads(json_str)
                if 'tool' in data:
                    return {
                        'tool': data['tool'],
                        'parameters': data.get('parameters', {})
                    }
    except (json.JSONDecodeError, ValueError):
        pass
    
    return None


def execute_skill_from_llm_response(
    response: str,
    original_query: str,
    context: Optional[Dict[str, Any]] = None
) -> tuple[Optional[SkillResult], str]:
    """
    Выполняет навык на основе ответа LLM.
    
    Args:
        response: Ответ от LLM
        original_query: Исходный запрос пользователя
        context: Дополнительный контекст
    
    Returns:
        Кортеж (SkillResult или None, очищенный ответ без JSON)
    """
    skill_call = parse_skill_call_from_response(response)
    
    if not skill_call:
        # Нет вызова навыка, возвращаем исходный ответ
        return None, response
    
    skill_name = skill_call.get('tool')
    parameters = skill_call.get('parameters', {})
    
    if not skill_name:
        return None, response
    
    manager = get_skills_manager()
    skill_result = manager.execute_skill(skill_name, original_query, parameters, context)
    
    # Удаляем JSON из ответа
    cleaned_response = response
    for pattern in [
        r'\{[^{}]*"tool"[^{}]*\}',
        r'```json\s*\{[^{}]*"tool"[^{}]*\}\s*```',
        r'```\s*\{[^{}]*"tool"[^{}]*\}\s*```',
    ]:
        import re
        cleaned_response = re.sub(pattern, '', cleaned_response, flags=re.DOTALL | re.IGNORECASE)
    
    cleaned_response = cleaned_response.strip()
    
    return skill_result, cleaned_response

