"""
Менеджер навыков для AI ассистента.
Управляет регистрацией, обнаружением и выполнением навыков.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from .base import BaseSkill, SkillResult

logger = logging.getLogger(__name__)


class SkillsManager:
    """
    Менеджер для управления навыками AI ассистента.
    
    Автоматически обнаруживает и регистрирует навыки из модулей системы.
    """
    
    def __init__(self):
        self._skills: Dict[str, BaseSkill] = {}
        self._initialized = False
    
    def register_skill(self, skill: BaseSkill) -> None:
        """
        Регистрирует навык.
        
        Args:
            skill: Экземпляр навыка
        """
        if not isinstance(skill, BaseSkill):
            raise TypeError(f"Навык должен быть экземпляром BaseSkill, получен {type(skill)}")
        
        if skill.name in self._skills:
            logger.warning(f"Навык '{skill.name}' уже зарегистрирован, перезаписываем")
        
        self._skills[skill.name] = skill
        logger.info(f"Зарегистрирован навык: {skill.name}")
    
    def register_skills(self, skills: List[BaseSkill]) -> None:
        """Регистрирует несколько навыков."""
        for skill in skills:
            self.register_skill(skill)
    
    def get_skill(self, name: str) -> Optional[BaseSkill]:
        """Получает навык по имени."""
        return self._skills.get(name)
    
    def get_all_skills(self) -> List[BaseSkill]:
        """Возвращает все зарегистрированные навыки."""
        return list(self._skills.values())
    
    # Метод find_applicable_skills больше не используется!
    # Все навыки всегда доступны LLM, который сам выбирает подходящие
    
    def execute_skill(self, skill_name: str, query: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        """
        Выполняет навык по имени.
        
        Args:
            skill_name: Имя навыка
            query: Запрос пользователя
            parameters: Параметры для выполнения
            context: Дополнительный контекст
        
        Returns:
            SkillResult с результатом выполнения
        """
        skill = self.get_skill(skill_name)
        if not skill:
            return SkillResult(
                success=False,
                error=f"Навык '{skill_name}' не найден"
            )
        
        try:
            return skill.execute(query, parameters, context)
        except Exception as e:
            logger.exception(f"Ошибка выполнения навыка {skill_name}")
            return SkillResult(
                success=False,
                error=f"Ошибка выполнения навыка: {str(e)}"
            )
    
    def get_function_definitions(self) -> List[Dict[str, Any]]:
        """
        Возвращает определения всех функций для LLM (function calling).
        
        Returns:
            Список определений функций в формате OpenAI function calling
        """
        return [skill.get_function_definition() for skill in self._skills.values()]
    
    def auto_discover_skills(self) -> None:
        """
        Автоматически обнаруживает и регистрирует навыки из модулей системы.
        
        Ищет навыки в:
        - core/api/src/core/ai_assistant/skills/builtin/ - встроенные навыки (рекурсивно по подпапкам)
        - modules/*/ai_assistant/skills/ - навыки модулей (TODO)
        
        Навыки должны находиться в файлах с именем *_skill.py
        """
        if self._initialized:
            return
        
        import importlib
        import os
        from pathlib import Path
        
        # Регистрируем встроенные навыки (рекурсивно по подпапкам)
        builtin_skills_path = Path(__file__).parent / 'builtin'
        if builtin_skills_path.exists():
            # Рекурсивно ищем все файлы *_skill.py
            for skill_file in builtin_skills_path.rglob('*_skill.py'):
                if skill_file.name.startswith('_'):
                    continue
                
                try:
                    # Формируем путь модуля относительно builtin
                    relative_path = skill_file.relative_to(builtin_skills_path.parent)
                    # Преобразуем путь в имя модуля (заменяем / на . и убираем .py)
                    module_path = str(relative_path.with_suffix('')).replace('/', '.').replace('\\', '.')
                    module_name = f"src.core.ai_assistant.skills.{module_path}"
                    module = importlib.import_module(module_name)
                    
                    # Ищем классы, наследующиеся от BaseSkill
                    for attr_name in dir(module):
                        if attr_name.startswith('_'):
                            continue
                        attr = getattr(module, attr_name)
                        if (isinstance(attr, type) and 
                            issubclass(attr, BaseSkill) and 
                            attr != BaseSkill):
                            try:
                                skill_instance = attr()
                                self.register_skill(skill_instance)
                            except Exception as e:
                                logger.warning(f"Не удалось создать экземпляр навыка {attr_name}: {e}")
                except Exception as e:
                    logger.warning(f"Не удалось загрузить навык из {skill_file}: {e}")
        
        # Регистрируем навыки из модулей
        # TODO: Реализовать поиск навыков в модулях
        
        self._initialized = True
        logger.info(f"Автоматическое обнаружение завершено. Зарегистрировано {len(self._skills)} навыков")
    
    def clear(self) -> None:
        """Очищает все зарегистрированные навыки."""
        self._skills.clear()
        self._initialized = False


# Глобальный экземпляр менеджера навыков
_skills_manager: Optional[SkillsManager] = None


def get_skills_manager() -> SkillsManager:
    """Возвращает глобальный экземпляр менеджера навыков."""
    global _skills_manager
    if _skills_manager is None:
        _skills_manager = SkillsManager()
        _skills_manager.auto_discover_skills()
    return _skills_manager

