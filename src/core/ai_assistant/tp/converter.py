"""
Конвертация DOCX в Markdown: mammoth (DOCX → HTML) и html2text (HTML → Markdown).
Таблицы постобрабатываются: подряд идущие ячейки с одинаковым значением объединяются (colspan).
"""
import re
from html import escape
from typing import List, Optional, Tuple

import html2text
import mammoth


def _merge_same_cells_in_row(cells: List[str]) -> List[Tuple[str, int]]:
    """Объединяет подряд идущие одинаковые ячейки в (значение, colspan)."""
    if not cells:
        return []
    merged: List[Tuple[str, int]] = []
    for c in cells:
        if merged and merged[-1][0] == c:
            merged[-1] = (merged[-1][0], merged[-1][1] + 1)
        else:
            merged.append((c, 1))
    return merged


def _md_table_to_html_with_colspan(md_table_lines: List[str]) -> str:
    """Превращает markdown-таблицу в HTML с объединёнными ячейками (colspan)."""
    rows = []
    for line in md_table_lines:
        line = line.strip()
        if not line or not line.startswith("|") or not line.endswith("|"):
            continue
        parts = [p.strip() for p in line.split("|")][1:-1]
        if not parts:
            continue
        if re.match(r"^[\s\-:]+$", "".join(parts)):
            continue
        rows.append(parts)
    if not rows:
        return "\n".join(md_table_lines)
    out = ["<table>"]
    for row_cells in rows:
        merged = _merge_same_cells_in_row(row_cells)
        tds = "".join(
            f'<td colspan="{span}">{escape(cell)}</td>' if span > 1 else f"<td>{escape(cell)}</td>"
            for cell, span in merged
        )
        out.append(f"<tr>{tds}</tr>")
    out.append("</table>")
    return "\n".join(out)


def _tables_merge_same_cells(md: str) -> str:
    """Находит markdown-таблицы и заменяет их на HTML с объединёнными ячейками."""
    lines = md.split("\n")
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("|") and line.strip().endswith("|"):
            table_lines = [line]
            j = i + 1
            while j < len(lines) and lines[j].strip().startswith("|") and lines[j].strip().endswith("|"):
                table_lines.append(lines[j])
                j += 1
            has_sep = any(re.search(r"\-+", ln) for ln in table_lines)
            if has_sep and len(table_lines) >= 2:
                result.append(_md_table_to_html_with_colspan(table_lines))
                i = j
                continue
        result.append(line)
        i += 1
    return "\n".join(result)


class TPDocumentConverter:
    """Конвертация DOCX в Markdown через mammoth + html2text."""

    @staticmethod
    def docx_to_markdown(file_path: Optional[str] = None, file_obj=None) -> str:
        if file_obj is not None:
            file_obj.seek(0)
            docx_file = file_obj
            should_close = False
        elif file_path:
            docx_file = open(file_path, "rb")
            should_close = True
        else:
            raise ValueError("Не указан ни путь к файлу, ни файловый объект")

        try:
            result = mammoth.convert_to_html(docx_file)
            html = result.value
            converter = html2text.HTML2Text()
            converter.ignore_links = True
            converter.ignore_images = True
            md = converter.handle(html)
            md = _tables_merge_same_cells(md)
            out = md.strip()
            if not out:
                raise ValueError("Документ пуст или не удалось извлечь контент")
            return out
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Ошибка конвертации DOCX в Markdown: {e}") from e
        finally:
            if should_close:
                docx_file.close()
