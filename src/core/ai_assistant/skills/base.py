"""
Базовый класс для навыков AI ассистента.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass
class SkillResult:
    """Результат выполнения навыка."""
    success: bool
    result: Any = None
    error: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Преобразует результат в словарь."""
        return {
            'success': self.success,
            'result': self.result,
            'error': self.error,
            'metadata': self.metadata or {},
        }


class BaseSkill(ABC):
    """
    Базовый класс для всех навыков AI ассистента.
    
    Каждый навык должен:
    1. Описать себя (название, описание, параметры)
    2. Определить, может ли он обработать запрос
    3. Выполнить действие
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Уникальное имя навыка (например: 'math_calculator', 'document_creator')."""
        pass
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """Отображаемое название навыка на русском (например: 'Калькулятор', 'Документы')."""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Описание навыка для LLM (что он делает, когда использовать)."""
        pass
    
    @property
    def parameters(self) -> Dict[str, Any]:
        """
        Описание параметров навыка в формате JSON Schema для function calling.
        
        Returns:
            Словарь с описанием параметров в формате:
            {
                "type": "object",
                "properties": {
                    "param_name": {
                        "type": "string",
                        "description": "Описание параметра"
                    }
                },
                "required": ["param_name"]
            }
        """
        return {
            "type": "object",
            "properties": {},
            "required": []
        }
    
    # Метод can_handle больше не используется!
    # LLM сам определяет, какой навык использовать на основе описания
    
    @abstractmethod
    def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        """
        Выполняет навык.
        
        Args:
            query: Запрос пользователя
            parameters: Параметры для выполнения (из function calling)
            context: Дополнительный контекст (модуль, сессия, пользователь и т.д.)
        
        Returns:
            SkillResult с результатом выполнения
        """
        pass
    
    def get_function_definition(self) -> Dict[str, Any]:
        """
        Возвращает определение функции для LLM (function calling).
        
        Returns:
            Словарь с определением функции в формате OpenAI function calling
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
    
    def __str__(self) -> str:
        return f"Skill({self.name})"
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name='{self.name}')>"

