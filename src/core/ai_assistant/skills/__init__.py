"""
Система модульных навыков для AI ассистента.

Навыки (skills) - это модульные компоненты, которые могут выполнять различные действия:
- Математические вычисления
- Создание документов
- Работа с файлами
- И многое другое

Навыки автоматически определяются AI и выполняются при необходимости.
"""

from .base import BaseSkill, SkillResult
from .manager import SkillsManager, get_skills_manager
from .registry import SkillRegistry

__all__ = [
    'BaseSkill',
    'SkillResult',
    'SkillsManager',
    'get_skills_manager',
    'SkillRegistry',
]

