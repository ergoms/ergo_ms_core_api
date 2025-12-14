"""
Генератор PDF документов из Markdown.
Использует reportlab для генерации PDF.
"""
import re
from pathlib import Path
from typing import List, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, 
    ListFlowable, ListItem, HRFlowable
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


class PDFGenerator:
    """Генератор PDF документов из Markdown."""
    
    def __init__(self):
        self._styles = None
        self._register_fonts()
    
    def _register_fonts(self) -> None:
        """Регистрирует шрифты для PDF."""
        # Используем встроенные шрифты, которые поддерживают кириллицу
        # В реальном проекте можно зарегистрировать DejaVu или другие TTF
        pass
    
    def _get_styles(self):
        """Возвращает стили для PDF."""
        if self._styles is None:
            self._styles = getSampleStyleSheet()
            
            # Основной стиль
            self._styles.add(ParagraphStyle(
                name='CustomNormal',
                parent=self._styles['Normal'],
                fontSize=12,
                leading=18,
                spaceBefore=6,
                spaceAfter=6,
                alignment=TA_JUSTIFY,
            ))
            
            # Заголовок 1
            self._styles.add(ParagraphStyle(
                name='CustomHeading1',
                parent=self._styles['Heading1'],
                fontSize=18,
                leading=24,
                spaceBefore=12,
                spaceAfter=12,
                textColor=colors.black,
            ))
            
            # Заголовок 2
            self._styles.add(ParagraphStyle(
                name='CustomHeading2',
                parent=self._styles['Heading2'],
                fontSize=14,
                leading=20,
                spaceBefore=10,
                spaceAfter=8,
                textColor=colors.black,
            ))
            
            # Заголовок 3
            self._styles.add(ParagraphStyle(
                name='CustomHeading3',
                parent=self._styles['Heading3'],
                fontSize=12,
                leading=16,
                spaceBefore=8,
                spaceAfter=6,
                textColor=colors.black,
            ))
            
            # Курсив для подписей
            self._styles.add(ParagraphStyle(
                name='Italic',
                parent=self._styles['Normal'],
                fontSize=10,
                leading=14,
                textColor=colors.grey,
                alignment=TA_CENTER,
            ))
        
        return self._styles
    
    def generate(self, markdown_content: str, output_path: Path, title: str = "") -> Path:
        """
        Генерирует PDF документ из Markdown.
        
        Args:
            markdown_content: Содержимое в формате Markdown
            output_path: Путь для сохранения документа
            title: Заголовок документа (для метаданных)
        
        Returns:
            Путь к созданному файлу
        """
        output_path = Path(output_path)
        if not output_path.suffix:
            output_path = output_path.with_suffix('.pdf')
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Создаём документ
        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=A4,
            leftMargin=2.5*cm,
            rightMargin=2.5*cm,
            topMargin=2.5*cm,
            bottomMargin=2.5*cm,
            title=title,
        )
        
        # Парсим Markdown и создаём элементы
        elements = self._parse_markdown(markdown_content)
        
        # Генерируем PDF
        doc.build(elements)
        
        return output_path
    
    def _parse_markdown(self, content: str) -> List:
        """Парсит Markdown и возвращает список элементов для PDF."""
        styles = self._get_styles()
        elements = []
        lines = content.split('\n')
        i = 0
        
        # Собираем элементы списка для группировки
        list_items = []
        list_type = None  # 'bullet' или 'number'
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # Если есть накопленные элементы списка и текущая строка - не список
            if list_items and not stripped.startswith('- ') and \
               not stripped.startswith('* ') and not re.match(r'^\d+\.\s', stripped):
                elements.append(self._create_list(list_items, list_type, styles))
                list_items = []
                list_type = None
            
            # Пустая строка
            if not stripped:
                i += 1
                continue
            
            # Заголовки
            if stripped.startswith('#'):
                level = len(stripped) - len(stripped.lstrip('#'))
                text = stripped.lstrip('#').strip()
                text = self._convert_inline_formatting(text)
                
                if level == 1:
                    elements.append(Paragraph(text, styles['CustomHeading1']))
                elif level == 2:
                    elements.append(Paragraph(text, styles['CustomHeading2']))
                else:
                    elements.append(Paragraph(text, styles['CustomHeading3']))
                i += 1
                continue
            
            # Горизонтальная линия
            if stripped in ['---', '***', '___']:
                elements.append(Spacer(1, 6))
                elements.append(HRFlowable(
                    width="100%",
                    thickness=1,
                    color=colors.grey,
                    spaceBefore=6,
                    spaceAfter=6,
                ))
                i += 1
                continue
            
            # Маркированный список
            if stripped.startswith('- ') or stripped.startswith('* '):
                text = stripped[2:].strip()
                text = self._convert_inline_formatting(text)
                list_items.append(text)
                list_type = 'bullet'
                i += 1
                continue
            
            # Нумерованный список
            if re.match(r'^\d+\.\s', stripped):
                text = re.sub(r'^\d+\.\s', '', stripped)
                text = self._convert_inline_formatting(text)
                list_items.append(text)
                list_type = 'number'
                i += 1
                continue
            
            # Курсив для подписей (строки начинающиеся с *)
            if stripped.startswith('*') and stripped.endswith('*') and len(stripped) > 2:
                text = stripped[1:-1]
                elements.append(Paragraph(text, styles['Italic']))
                i += 1
                continue
            
            # Обычный параграф
            text = self._convert_inline_formatting(stripped)
            elements.append(Paragraph(text, styles['CustomNormal']))
            i += 1
        
        # Добавляем оставшиеся элементы списка
        if list_items:
            elements.append(self._create_list(list_items, list_type, styles))
        
        return elements
    
    def _create_list(self, items: List[str], list_type: str, styles) -> ListFlowable:
        """Создаёт список для PDF."""
        bullet_type = 'bullet' if list_type == 'bullet' else '1'
        
        list_items = []
        for item in items:
            list_items.append(ListItem(
                Paragraph(item, styles['CustomNormal']),
                leftIndent=20,
            ))
        
        return ListFlowable(
            list_items,
            bulletType=bullet_type,
            start=1 if list_type == 'number' else None,
        )
    
    def _convert_inline_formatting(self, text: str) -> str:
        """Конвертирует Markdown форматирование в ReportLab теги."""
        # Жирный текст
        text = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', text)
        text = re.sub(r'__([^_]+)__', r'<b>\1</b>', text)
        
        # Курсив
        text = re.sub(r'\*([^*]+)\*', r'<i>\1</i>', text)
        text = re.sub(r'_([^_]+)_', r'<i>\1</i>', text)
        
        return text

