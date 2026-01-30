from typing import Optional
from io import BytesIO

try:
    from docx import Document
except ImportError:
    Document = None


class TPDocumentConverter:
    @staticmethod
    def docx_to_markdown(file_path: Optional[str] = None, file_obj: Optional[BytesIO] = None) -> str:
        if Document is None:
            raise ValueError(
                "Модуль python-docx не установлен. "
                "Установите: poetry add python-docx"
            )
        try:
            if file_obj:
                file_obj.seek(0)
                doc = Document(file_obj)
            elif file_path:
                doc = Document(file_path)
            else:
                raise ValueError("Не указан ни путь к файлу, ни файловый объект")
            markdown_parts = []
            for element in doc.element.body:
                if element.tag.endswith('p'):
                    paragraph = None
                    for p in doc.paragraphs:
                        if p._element == element:
                            paragraph = p
                            break
                    if paragraph and paragraph.text.strip():
                        markdown_text = TPDocumentConverter._paragraph_to_markdown(paragraph)
                        if markdown_text:
                            markdown_parts.append(markdown_text)
                elif element.tag.endswith('tbl'):
                    table = None
                    for t in doc.tables:
                        if t._element == element:
                            table = t
                            break
                    if table:
                        markdown_table = TPDocumentConverter._table_to_markdown(table)
                        if markdown_table:
                            markdown_parts.append(markdown_table)
            result = "\n\n".join(markdown_parts)
            if not result.strip():
                raise ValueError("Документ пуст или не удалось извлечь контент")
            return result.strip()
        except Exception as e:
            if isinstance(e, ValueError):
                raise
            raise ValueError(f"Ошибка конвертации DOCX в Markdown: {str(e)}") from e

    @staticmethod
    def _paragraph_to_markdown(paragraph) -> str:
        text = paragraph.text.strip()
        if not text:
            return ""
        style = paragraph.style.name if paragraph.style else None
        if style and style.startswith('Heading'):
            level = 1
            if 'Heading 2' in style:
                level = 2
            elif 'Heading 3' in style:
                level = 3
            elif 'Heading 4' in style:
                level = 4
            elif 'Heading 5' in style:
                level = 5
            elif 'Heading 6' in style:
                level = 6
            return f"{'#' * level} {text}"
        return TPDocumentConverter._format_runs(paragraph.runs)

    @staticmethod
    def _format_runs(runs) -> str:
        result = []
        for run in runs:
            text = run.text
            if not text:
                continue
            if run.bold:
                text = f"**{text}**"
            if run.italic:
                text = f"*{text}*"
            if run.underline:
                text = f"<u>{text}</u>"
            result.append(text)
        return "".join(result)

    @staticmethod
    def _table_to_markdown(table) -> str:
        if not table.rows:
            return ""
        markdown_rows = []
        for row_idx, row in enumerate(table.rows):
            cells = []
            for cell in row.cells:
                cell_text = cell.text.strip()
                cell_text = " ".join(cell_text.split())
                cell_text = cell_text.replace("|", "\\|").replace("\n", " ")
                cells.append(cell_text or " ")
            markdown_row = "| " + " | ".join(cells) + " |"
            markdown_rows.append(markdown_row)
            if row_idx == 0:
                separator = "| " + " | ".join(["---"] * len(cells)) + " |"
                markdown_rows.append(separator)
        return "\n".join(markdown_rows)
