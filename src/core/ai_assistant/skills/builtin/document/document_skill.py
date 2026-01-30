"""
Навык для создания документов PDF.
Использует MD шаблоны и генераторы документов.
"""
import uuid
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

from django.conf import settings

from ...base import BaseSkill, SkillResult
from .template_loader import get_template_loader
from .generators import PDFGenerator


class DocumentSkill(BaseSkill):
    """Навык для создания документов PDF на основе шаблонов."""
    
    def __init__(self):
        self._pdf_generator = PDFGenerator()
        self._template_loader = get_template_loader()
    
    @property
    def name(self) -> str:
        return "create_document"
    
    @property
    def display_name(self) -> str:
        return "Документы"
    
    @property
    def description(self) -> str:
        templates_info = self._template_loader.get_templates_description()
        return f"""Создает документ PDF на основе шаблонов.

ИСПОЛЬЗУЙ ТОЛЬКО когда пользователь ЯВНО просит создать/сформировать/выгрузить документ:
- "создай документ", "сделай файл", "запиши в документ"
- "сформируй отчёт", "выгрузи отчёт", "экспортируй в файл"
- "сохрани как документ", "создай PDF"

НЕ используй этот навык если:
- Пользователь просто задает вопрос или просит объяснить что-то
- В ответе упоминается слово "документ" в контексте информации (например: "в документе указано...")
- Пользователь просит найти информацию или проиндексировать документ
- Это обычный вопрос к базе знаний (RAG)

Этот навык только для СОЗДАНИЯ нового файла, а не для работы с существующими документами.

{templates_info}"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        templates = self._template_loader.get_all_templates()
        template_ids = [t.id for t in templates] if templates else ["report", "analysis"]
        
        return {
            "type": "object",
            "properties": {
                "template": {
                    "type": "string",
                    "enum": template_ids,
                    "description": f"ID шаблона документа: {', '.join(template_ids)}"
                },
                "format": {
                    "type": "string",
                    "enum": ["pdf"],
                    "description": "Формат документа: pdf",
                    "default": "pdf"
                },
                "title": {
                    "type": "string",
                    "description": "Заголовок документа"
                },
                "content": {
                    "type": "string",
                    "description": "Основное содержимое документа"
                },
                "summary": {
                    "type": "string",
                    "description": "Краткое резюме (для шаблона analysis)"
                },
                "analysis": {
                    "type": "string",
                    "description": "Детальный анализ (для шаблона analysis)"
                },
                "conclusions": {
                    "type": "string",
                    "description": "Выводы (для шаблона analysis)"
                },
                "recommendations": {
                    "type": "string",
                    "description": "Рекомендации (для шаблона analysis)"
                },
                "author": {
                    "type": "string",
                    "description": "Автор документа"
                },
            },
            "required": ["template", "title"]
        }
    
    def execute(
        self, 
        query: str, 
        parameters: Optional[Dict[str, Any]] = None, 
        context: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """Создает документ на основе шаблона."""
        if not parameters:
            return SkillResult(
                success=False,
                error="Не указаны параметры для создания документа"
            )
        
        template_id = parameters.get('template', 'report')
        doc_format = parameters.get('format', 'pdf')
        title = parameters.get('title', 'Документ')
        
        # Проверяем формат - Word отчеты отключены
        if doc_format == 'docx':
            return SkillResult(
                success=False,
                error="Формирование Word отчетов отключено. Используйте формат PDF."
            )
        
        # Получаем шаблон
        template = self._template_loader.get_template(template_id)
        if not template:
            # Используем базовый шаблон если указанный не найден
            template = self._template_loader.get_template('report')
            if not template:
                return self._create_simple_document(parameters, doc_format, context)
        
        # Собираем переменные для шаблона
        variables = {
            'title': title,
            'author': parameters.get('author', 'AI Ассистент'),
            'date': datetime.now().strftime('%d.%m.%Y'),
            'content': parameters.get('content', ''),
            'summary': parameters.get('summary', ''),
            'analysis': parameters.get('analysis', ''),
            'conclusions': parameters.get('conclusions', ''),
            'recommendations': parameters.get('recommendations', ''),
        }
        
        # Рендерим шаблон
        rendered_content = template.render(variables)
        
        # Генерируем документ
        try:
            output_path = self._get_output_path(title, doc_format, context)
            
            # Только PDF формат поддерживается
            file_path = self._pdf_generator.generate(
                rendered_content, 
                output_path, 
                title=title
            )
            
            # Сохраняем информацию о документе в БД
            document_info = self._save_document_info(
                title=title,
                file_path=file_path,
                doc_format=doc_format,
                template_id=template_id,
                context=context
            )
            
            # Формируем ссылку на скачивание
            download_url = self._get_download_url(file_path)
            filename = file_path.name
            
            return SkillResult(
                success=True,
                result=f"Документ '{title}' успешно создан.\n\n📄 [Скачать {filename}]({download_url})",
                metadata={
                    'document_id': document_info.get('id'),
                    'file_path': str(file_path),
                    'filename': filename,
                    'download_url': download_url,
                    'format': doc_format,
                    'template': template_id,
                }
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"Ошибка создания документа: {str(e)}"
            )
    
    def _create_simple_document(
        self, 
        parameters: Dict[str, Any], 
        doc_format: str, 
        context: Optional[Dict[str, Any]]
    ) -> SkillResult:
        """Создает простой документ без шаблона."""
        # Проверяем формат - Word отчеты отключены
        if doc_format == 'docx':
            return SkillResult(
                success=False,
                error="Формирование Word отчетов отключено. Используйте формат PDF."
            )
        
        title = parameters.get('title', 'Документ')
        content = parameters.get('content', '')
        
        # Простой Markdown
        markdown_content = f"""# {title}

**Автор:** {parameters.get('author', 'AI Ассистент')}  
**Дата:** {datetime.now().strftime('%d.%m.%Y')}

---

{content}

---

*Документ сгенерирован системой ERGO MS*
"""
        
        try:
            output_path = self._get_output_path(title, doc_format, context)
            
            # Только PDF формат поддерживается
            file_path = self._pdf_generator.generate(
                markdown_content, 
                output_path, 
                title=title
            )
            
            document_info = self._save_document_info(
                title=title,
                file_path=file_path,
                doc_format=doc_format,
                template_id='simple',
                context=context
            )
            
            # Формируем ссылку на скачивание
            download_url = self._get_download_url(file_path)
            filename = file_path.name
            
            return SkillResult(
                success=True,
                result=f"Документ '{title}' успешно создан.\n\n📄 [Скачать {filename}]({download_url})",
                metadata={
                    'document_id': document_info.get('id'),
                    'file_path': str(file_path),
                    'filename': filename,
                    'download_url': download_url,
                    'format': doc_format,
                }
            )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"Ошибка создания документа: {str(e)}"
            )
    
    def _get_output_path(
        self, 
        title: str, 
        doc_format: str, 
        context: Optional[Dict[str, Any]]
    ) -> Path:
        """Возвращает путь для сохранения документа."""
        # Используем настройки из settings
        base_dir = getattr(settings, 'GENERATED_DOCUMENTS_DIR', None)
        if not base_dir:
            base_dir = Path(settings.BASE_DIR).parent / 'generated_documents'
        else:
            base_dir = Path(base_dir)
        
        # Добавляем папку пользователя если есть
        user = context.get('user') if context else None
        if user and hasattr(user, 'id'):
            base_dir = base_dir / f'user_{user.id}'
        
        # Создаём уникальное имя файла
        safe_title = "".join(c for c in title if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_title = safe_title[:50] or 'document'
        unique_id = str(uuid.uuid4())[:8]
        filename = f"{safe_title}_{unique_id}.{doc_format}"
        
        return base_dir / filename
    
    def _save_document_info(
        self,
        title: str,
        file_path: Path,
        doc_format: str,
        template_id: str,
        context: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Сохраняет информацию о документе в БД."""
        try:
            from ....models import KnowledgeDocument
            
            user = context.get('user') if context else None
            
            document = KnowledgeDocument.objects.create(
                user=user,
                title=title,
                content=f"Документ в формате {doc_format.upper()}",
                file_type=doc_format,
                source='ai_assistant_skill',
                metadata={
                    'created_by': 'ai_assistant',
                    'skill': 'document_creation',
                    'template': template_id,
                    'file_path': str(file_path),
                }
            )
            
            return {
                'id': str(document.id),
                'title': document.title,
            }
        except Exception:
            # Если не удалось сохранить в БД, возвращаем пустой результат
            return {'id': None, 'title': title}
    
    def _get_download_url(self, file_path: Path) -> str:
        """Возвращает URL для скачивания документа."""
        # Получаем относительный путь от MEDIA_ROOT
        media_root = Path(settings.MEDIA_ROOT)
        
        try:
            relative_path = file_path.relative_to(media_root)
            # Формируем URL через API endpoint
            return f"/api/ai_assistant/documents/download/{relative_path}"
        except ValueError:
            # Если файл не в MEDIA_ROOT, используем имя файла
            return f"/api/ai_assistant/documents/download/{file_path.name}"
