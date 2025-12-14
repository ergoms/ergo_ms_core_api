"""
Навык для создания графиков через ApexCharts.
Генерирует конфигурацию графика для отрисовки на фронтенде.
"""
from typing import Any, Dict, Optional

from ...base import BaseSkill, SkillResult


class ChartSkill(BaseSkill):
    """Навык для создания графиков на основе данных."""
    
    @property
    def name(self) -> str:
        return "create_chart"
    
    @property
    def display_name(self) -> str:
        return "Графики"
    
    @property
    def description(self) -> str:
        return """Создает график на основе данных.
Используй ТОЛЬКО когда пользователь ЯВНО просит: "построй график", "создай график", "покажи график", "визуализируй данные", "нарисуй график".
НЕ используй для простых ответов текстом.

ВАЖНО: Если пользователь просит построить график в модуле BI и в предыдущих сообщениях есть данные (таблица), 
используй эти данные для графика. Параметр "data" можно не указывать - данные будут взяты автоматически из последнего ответа с данными.

Поддерживаемые типы графиков:
- line: линейный график (для временных рядов, трендов)
- bar: столбчатая диаграмма (для сравнения категорий)
- pie: круговая диаграмма (для долей, процентов)
- area: площадной график (для накопленных значений)
- scatter: точечная диаграмма (для корреляций)"""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "chart_type": {
                    "type": "string",
                    "enum": ["line", "bar", "pie", "area", "scatter"],
                    "description": "Тип графика: line (линейный), bar (столбчатый), pie (круговой), area (площадной), scatter (точечный)",
                    "default": "line"
                },
                "title": {
                    "type": "string",
                    "description": "Заголовок графика"
                },
                "data": {
                    "type": "array",
                    "description": "Массив данных для графика. Для line/bar/area/scatter: массив объектов {x: значение, y: значение}. Для pie: массив объектов {label: название, value: значение}. Если не указано и есть данные в контексте BI, будут использованы они",
                    "items": {
                        "type": "object"
                    }
                },
                "x_axis_label": {
                    "type": "string",
                    "description": "Подпись оси X (для line, bar, area, scatter)"
                },
                "y_axis_label": {
                    "type": "string",
                    "description": "Подпись оси Y (для line, bar, area, scatter)"
                },
                "series_name": {
                    "type": "string",
                    "description": "Название серии данных (для line, bar, area, scatter)",
                    "default": "Данные"
                },
                "colors": {
                    "type": "array",
                    "description": "Массив цветов в формате HEX (например, ['#10B981', '#3B82F6']). Если не указано, используются цвета по умолчанию",
                    "items": {
                        "type": "string"
                    }
                },
                "show_legend": {
                    "type": "boolean",
                    "description": "Показывать ли легенду",
                    "default": True
                },
                "height": {
                    "type": "number",
                    "description": "Высота графика в пикселях",
                    "default": 400
                }
            },
            "required": ["chart_type", "title"]
        }
    
    def execute(
        self, 
        query: str, 
        parameters: Optional[Dict[str, Any]] = None, 
        context: Optional[Dict[str, Any]] = None
    ) -> SkillResult:
        """Создает конфигурацию графика."""
        if not parameters:
            return SkillResult(
                success=False,
                error="Не указаны параметры для создания графика"
            )
        
        chart_type = parameters.get("chart_type", "line")
        title = parameters.get("title", "График")
        data = parameters.get("data", [])
        
        # Если данных нет в параметрах, пытаемся взять из контекста BI
        if not data and context:
            session = context.get("session")
            if session:
                # Получаем последнее сообщение с данными из этой сессии
                from src.core.ai_assistant.models import ChatMessage
                last_data_message = ChatMessage.objects.filter(
                    session=session,
                    message_type=ChatMessage.MESSAGE_TYPE_ASSISTANT,
                    metadata__isnull=False
                ).exclude(
                    metadata__data__isnull=True
                ).order_by('-created_at').first()
                
                if last_data_message and last_data_message.metadata:
                    bi_data = last_data_message.metadata.get("data", [])
                    bi_columns = last_data_message.metadata.get("columns", [])
                    
                    if bi_data and bi_columns:
                        # Преобразуем данные BI в формат для графика
                        data = self._convert_bi_data_to_chart_data(
                            bi_data, 
                            bi_columns, 
                            chart_type
                        )
        
        if not data:
            return SkillResult(
                success=False,
                error="Не указаны данные для графика и нет данных в контексте BI"
            )
        
        # Валидация данных
        if chart_type == "pie":
            # Для pie нужны label и value
            validated_data = []
            for item in data:
                if isinstance(item, dict):
                    label = item.get("label") or item.get("name") or str(item.get("x", ""))
                    value = item.get("value") or item.get("y", 0)
                    try:
                        value = float(value)
                    except (ValueError, TypeError):
                        value = 0
                    validated_data.append({"label": str(label), "value": value})
        else:
            # Для остальных типов нужны x и y
            validated_data = []
            for item in data:
                if isinstance(item, dict):
                    x = item.get("x") or item.get("label") or item.get("name")
                    y = item.get("y") or item.get("value", 0)
                    try:
                        y = float(y)
                    except (ValueError, TypeError):
                        y = 0
                    validated_data.append({"x": x, "y": y})
        
        if not validated_data:
            return SkillResult(
                success=False,
                error="Не удалось обработать данные для графика"
            )
        
        # Формируем конфигурацию графика
        chart_config = {
            "chart_type": chart_type,
            "title": title,
            "data": validated_data,
            "x_axis_label": parameters.get("x_axis_label", ""),
            "y_axis_label": parameters.get("y_axis_label", ""),
            "series_name": parameters.get("series_name", "Данные"),
            "colors": parameters.get("colors", []),
            "show_legend": parameters.get("show_legend", True),
            "height": parameters.get("height", 400)
        }
        
        return SkillResult(
            success=True,
            result=f"График '{title}' создан",
            metadata={'chart_config': chart_config}
        )
    
    def _convert_bi_data_to_chart_data(
        self, 
        bi_data: list, 
        columns: list, 
        chart_type: str
    ) -> list:
        """
        Преобразует данные BI (список словарей) в формат для графика.
        
        Args:
            bi_data: Список словарей с данными из BI
            columns: Список названий колонок
            chart_type: Тип графика
        
        Returns:
            Список данных в формате для графика
        """
        if not bi_data or not columns:
            return []
        
        # Для pie графика используем первые две колонки (label, value)
        if chart_type == "pie":
            if len(columns) < 2:
                return []
            
            label_col = columns[0]
            value_col = columns[1]
            
            result = []
            for row in bi_data[:20]:  # Ограничиваем до 20 элементов для pie
                if isinstance(row, dict):
                    label = str(row.get(label_col, ""))
                    try:
                        value = float(row.get(value_col, 0))
                    except (ValueError, TypeError):
                        value = 0
                    if label and value:
                        result.append({"label": label, "value": value})
            return result
        
        # Для остальных типов используем первую колонку как X, вторую как Y
        else:
            if len(columns) < 2:
                return []
            
            x_col = columns[0]
            y_col = columns[1]
            
            result = []
            for row in bi_data[:100]:  # Ограничиваем до 100 элементов
                if isinstance(row, dict):
                    x = row.get(x_col, "")
                    try:
                        y = float(row.get(y_col, 0))
                    except (ValueError, TypeError):
                        y = 0
                    if x is not None:
                        result.append({"x": str(x), "y": y})
            return result

