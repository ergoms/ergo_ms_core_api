"""
Реестр навыков для автоматической регистрации.
"""
from typing import List

from .base import BaseSkill
from .manager import get_skills_manager


class SkillRegistry:
    """
    Реестр для регистрации навыков.
    
    Используется модулями для регистрации своих навыков.
    """
    
    @staticmethod
    def register(skill: BaseSkill) -> None:
        """Регистрирует навык."""
        manager = get_skills_manager()
        manager.register_skill(skill)
    
    @staticmethod
    def register_many(skills: List[BaseSkill]) -> None:
        """Регистрирует несколько навыков."""
        manager = get_skills_manager()
        manager.register_skills(skills)
    
    @staticmethod
    def get_all() -> List[BaseSkill]:
        """Возвращает все зарегистрированные навыки."""
        manager = get_skills_manager()
        return manager.get_all_skills()

