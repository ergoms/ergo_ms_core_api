"""
Навык для создания документов Word.
"""
from typing import Any, Dict, Optional

from ...base import BaseSkill, SkillResult
from ....models import KnowledgeDocument


class DocumentSkill(BaseSkill):
    """Навык для создания документов Word."""
    
    @property
    def name(self) -> str:
        return "create_document"
    
    @property
    def description(self) -> str:
        return """Создает документ Word (.docx) с указанным содержимым.
Используй этот навык когда пользователь просит:
- Создать документ
- Создать Word документ
- Сформировать документ с анализом
- Создать файл с информацией"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Название документа"
                },
                "content": {
                    "type": "string",
                    "description": "Содержимое документа (текст, который будет в документе)"
                },
                "format": {
                    "type": "string",
                    "enum": ["docx", "txt"],
                    "description": "Формат документа (docx для Word, txt для текстового)",
                    "default": "docx"
                }
            },
            "required": ["title", "content"]
        }
    
    # can_handle больше не используется - LLM сам определяет
    
    def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        """Создает документ."""
        if not parameters:
            return SkillResult(
                success=False,
                error="Не указаны параметры для создания документа"
            )
        
        title = parameters.get('title')
        content = parameters.get('content')
        format_type = parameters.get('format', 'docx')
        
        if not title or not content:
            return SkillResult(
                success=False,
                error="Не указаны название или содержимое документа"
            )
        
        # Получаем пользователя из контекста
        user = None
        if context and 'user' in context:
            user = context['user']
        
        if not user:
            return SkillResult(
                success=False,
                error="Пользователь не найден в контексте"
            )
        
        try:
            # Создаем документ в базе знаний
            document = KnowledgeDocument.objects.create(
                user=user,
                title=title,
                content=content,
                file_type=format_type,
                source='ai_assistant_skill',
                metadata={
                    'created_by': 'ai_assistant',
                    'skill': 'document_creation'
                }
            )
            
            return SkillResult(
                success=True,
                result=f"Документ '{title}' успешно создан",
                metadata={
                    'document_id': str(document.id),
                    'document_title': document.title,
                    'format': format_type,
                }
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"Ошибка создания документа: {str(e)}"
            )

