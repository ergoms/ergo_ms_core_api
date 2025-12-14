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
                    "description": "Массив данных для графика. Для line/bar/area/scatter: массив объектов {x: значение, y: значение}. Для pie: массив объектов {label: название, value: значение}",
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
            "required": ["chart_type", "title", "data"]
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
                message="Не указаны параметры для создания графика"
            )
        
        chart_type = parameters.get("chart_type", "line")
        title = parameters.get("title", "График")
        data = parameters.get("data", [])
        
        if not data:
            return SkillResult(
                success=False,
                message="Не указаны данные для графика"
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
                message="Не удалось обработать данные для графика"
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

