"""
Навыки для работы с документами.
"""
from .document_skill import DocumentSkill
from .template_loader import get_template_loader, TemplateLoader, DocumentTemplate

__all__ = [
    'DocumentSkill',
    'get_template_loader',
    'TemplateLoader',
    'DocumentTemplate',
]
