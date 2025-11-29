"""
Парсер математических выражений из естественного языка.
Использует SymPy для символьного парсинга и регулярные выражения.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class MathOperationType(Enum):
    """Типы математических операций."""
    ARITHMETIC = "arithmetic"          # Простая арифметика: 2+2
    ALGEBRA = "algebra"                # Алгебра: решить x^2 + 2x + 1 = 0
    CALCULUS_DERIVATIVE = "derivative" # Производная: d/dx(x^2)
    CALCULUS_INTEGRAL = "integral"     # Интеграл: ∫x^2 dx
    LIMIT = "limit"                    # Предел: lim(x->0) sin(x)/x
    SIMPLIFY = "simplify"              # Упростить выражение
    EXPAND = "expand"                  # Раскрыть скобки
    FACTOR = "factor"                  # Факторизация
    SOLVE = "solve"                    # Решить уравнение
    MATRIX = "matrix"                  # Матричные операции
    STATISTICS = "statistics"          # Статистика
    UNKNOWN = "unknown"


@dataclass
class ParsedMathExpression:
    """Результат парсинга математического выражения."""
    operation_type: MathOperationType
    expression: str
    variables: Dict[str, Any]
    original_text: str
    confidence: float  # 0.0 - 1.0


class MathExpressionParser:
    """
    Парсер для извлечения математических выражений из текста.
    """
    
    # Паттерны для распознавания типов операций
    OPERATION_PATTERNS = {
        MathOperationType.CALCULUS_DERIVATIVE: [
            r"производн\w*\s+(?:от\s+)?(.+?)(?:\s+по\s+(\w))?",
            r"d/d(\w)\s*\((.+?)\)",
            r"(?:найти|вычислить)\s+производную\s+(.+)",
        ],
        MathOperationType.CALCULUS_INTEGRAL: [
            r"интеграл\s+(?:от\s+)?(.+?)(?:\s+по\s+(\w))?",
            r"∫\s*(.+?)\s*d(\w)",
            r"проинтегрировать\s+(.+)",
        ],
        MathOperationType.LIMIT: [
            r"предел\s+(?:при\s+)?(\w)\s*(?:->|→|стремящемся к)\s*(.+?)\s+(?:от\s+)?(.+)",
            r"lim\s*\(\s*(\w)\s*(?:->|→)\s*(.+?)\s*\)\s*(.+)",
        ],
        MathOperationType.SOLVE: [
            r"реши(?:ть)?\s+(?:уравнение\s+)?(.+)",
            r"найти\s+(?:корни|решение)\s+(.+)",
            r"(.+?)\s*=\s*(.+)",
        ],
        MathOperationType.SIMPLIFY: [
            r"упрости(?:ть)?\s+(.+)",
            r"simplify\s+(.+)",
        ],
        MathOperationType.EXPAND: [
            r"раскрой(?:ть)?\s+(?:скобки\s+)?(.+)",
            r"expand\s+(.+)",
        ],
        MathOperationType.FACTOR: [
            r"факториз(?:овать|уй)\s+(.+)",
            r"разлож(?:ить)?\s+на\s+множители\s+(.+)",
            r"factor\s+(.+)",
        ],
        MathOperationType.STATISTICS: [
            r"(?:средн\w+|mean)\s+(?:от\s+)?(.+)",
            r"(?:дисперси\w+|variance)\s+(?:от\s+)?(.+)",
            r"(?:стандартн\w+\s+отклонени\w+|std)\s+(?:от\s+)?(.+)",
        ],
    }
    
    # Паттерны для чисел и выражений
    NUMBER_PATTERN = r'-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?'
    EXPRESSION_PATTERN = r'[\d\w\s+\-*/^().,=<>√πe]+'
    
    def __init__(self) -> None:
        self._compile_patterns()
    
    def _compile_patterns(self) -> None:
        """Компилирует регулярные выражения."""
        self._compiled_patterns: Dict[MathOperationType, List[re.Pattern]] = {}
        for op_type, patterns in self.OPERATION_PATTERNS.items():
            self._compiled_patterns[op_type] = [
                re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns
            ]
    
    def parse(self, text: str) -> ParsedMathExpression:
        """
        Парсит текст и извлекает математическое выражение.
        
        Args:
            text: Входной текст (например: "посчитай 2+2" или "найди производную x^2")
        
        Returns:
            ParsedMathExpression с типом операции и выражением
        """
        text = text.strip()
        
        # Проверяем специфичные операции
        for op_type, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                match = pattern.search(text)
                if match:
                    expression, variables = self._extract_from_match(match, op_type)
                    return ParsedMathExpression(
                        operation_type=op_type,
                        expression=expression,
                        variables=variables,
                        original_text=text,
                        confidence=0.9,
                    )
        
        # Пробуем извлечь простое арифметическое выражение
        arithmetic_expr = self._extract_arithmetic(text)
        if arithmetic_expr:
            return ParsedMathExpression(
                operation_type=MathOperationType.ARITHMETIC,
                expression=arithmetic_expr,
                variables={},
                original_text=text,
                confidence=0.7,
            )
        
        # Если ничего не нашли
        return ParsedMathExpression(
            operation_type=MathOperationType.UNKNOWN,
            expression=text,
            variables={},
            original_text=text,
            confidence=0.1,
        )
    
    def _extract_from_match(
        self, match: re.Match, op_type: MathOperationType
    ) -> Tuple[str, Dict[str, Any]]:
        """Извлекает выражение и переменные из match."""
        groups = match.groups()
        variables: Dict[str, Any] = {}
        
        if op_type == MathOperationType.CALCULUS_DERIVATIVE:
            expression = groups[0] if groups else ""
            if len(groups) > 1 and groups[1]:
                variables['variable'] = groups[1]
            else:
                variables['variable'] = 'x'
        
        elif op_type == MathOperationType.CALCULUS_INTEGRAL:
            expression = groups[0] if groups else ""
            if len(groups) > 1 and groups[1]:
                variables['variable'] = groups[1]
            else:
                variables['variable'] = 'x'
        
        elif op_type == MathOperationType.LIMIT:
            if len(groups) >= 3:
                variables['variable'] = groups[0]
                variables['point'] = groups[1]
                expression = groups[2]
            else:
                expression = groups[0] if groups else ""
        
        elif op_type == MathOperationType.SOLVE:
            if len(groups) >= 2 and groups[1]:
                # Уравнение вида "expr1 = expr2"
                expression = f"{groups[0]} - ({groups[1]})"
            else:
                expression = groups[0] if groups else ""
        
        else:
            expression = groups[0] if groups else ""
        
        return self._normalize_expression(expression), variables
    
    def _extract_arithmetic(self, text: str) -> Optional[str]:
        """Извлекает арифметическое выражение из текста."""
        # Удаляем слова-команды
        cleaned = re.sub(
            r'\b(посчитай|вычисли|сколько\s+будет|чему\s+равно|calculate|compute)\b',
            '',
            text,
            flags=re.IGNORECASE
        )
        
        # Ищем математическое выражение
        math_pattern = re.compile(
            r'[(\s]*' + self.NUMBER_PATTERN + r'[\s)]*'
            r'(?:[\s]*[+\-*/^%][\s]*[(\s]*' + self.NUMBER_PATTERN + r'[\s)]*)+',
            re.IGNORECASE
        )
        
        match = math_pattern.search(cleaned)
        if match:
            return self._normalize_expression(match.group())
        
        # Проверяем простое число
        number_match = re.search(self.NUMBER_PATTERN, cleaned)
        if number_match and number_match.group() == cleaned.strip():
            return number_match.group()
        
        return None
    
    def _normalize_expression(self, expr: str) -> str:
        """Нормализует выражение."""
        expr = expr.strip()
        # Замена символов
        replacements = {
            '×': '*',
            '÷': '/',
            '−': '-',
            '^': '**',
            '√': 'sqrt',
            'π': 'pi',
        }
        for old, new in replacements.items():
            expr = expr.replace(old, new)
        return expr
    
    def is_math_query(self, text: str) -> bool:
        """
        Проверяет, является ли текст математическим запросом.
        
        Args:
            text: Входной текст
        
        Returns:
            True если текст содержит математический запрос
        """
        math_keywords = [
            'посчитай', 'вычисли', 'сколько будет', 'чему равно',
            'calculate', 'compute', 'solve', 'find',
            'производн', 'интеграл', 'предел', 'упрост',
            'уравнен', 'корни', 'факториз',
            'derivative', 'integral', 'limit', 'simplify',
        ]
        
        text_lower = text.lower()
        
        # Проверяем ключевые слова
        if any(kw in text_lower for kw in math_keywords):
            return True
        
        # Проверяем наличие математических операторов
        if re.search(r'\d\s*[+\-*/^]\s*\d', text):
            return True
        
        # Проверяем математические символы
        if any(c in text for c in '∫√∑∏±÷×'):
            return True
        
        return False

