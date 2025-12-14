"""
Навык для математических вычислений.
Использует SymPy для символьной математики и NumPy для численных вычислений.
"""
from typing import Any, Dict, Optional
from dataclasses import dataclass

import numpy as np
import sympy

from ...base import BaseSkill, SkillResult


@dataclass
class MathResult:
    """Результат математического вычисления."""
    success: bool
    result: Any
    result_latex: Optional[str] = None
    result_pretty: Optional[str] = None
    error: Optional[str] = None
    operation_type: Optional[str] = None


class MathSkill(BaseSkill):
    """Навык для выполнения математических вычислений."""
    
    def __init__(self):
        self._symbols = {
            'x': sympy.Symbol('x'),
            'y': sympy.Symbol('y'),
            'z': sympy.Symbol('z'),
            'a': sympy.Symbol('a'),
            'b': sympy.Symbol('b'),
            'c': sympy.Symbol('c'),
            'n': sympy.Symbol('n', integer=True),
            't': sympy.Symbol('t'),
        }
    
    @property
    def name(self) -> str:
        return "math_calculator"
    
    @property
    def display_name(self) -> str:
        return "Калькулятор"
    
    @property
    def description(self) -> str:
        return """Выполняет математические вычисления: арифметика, алгебра, производные, интегралы.
Используй ТОЛЬКО когда пользователь ЯВНО просит ВЫЧИСЛИТЬ: "посчитай", "сколько будет", "вычисли".
НЕ используй для вопросов типа "что такое?" или объяснений."""
    
    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "Математическое выражение для вычисления (например: '2+2', 'sqrt(16)', 'x**2+2*x+1')"
                }
            },
            "required": ["expression"]
        }
    
    def execute(self, query: str, parameters: Optional[Dict[str, Any]] = None, context: Optional[Dict[str, Any]] = None) -> SkillResult:
        """Выполняет математическое вычисление."""
        if not parameters or 'expression' not in parameters:
            return SkillResult(
                success=False,
                error="Не указано выражение для вычисления"
            )

        expression = parameters['expression']

        try:
            result = self._calculate(expression)
            if result.success:
                formatted = self._format_result(result)
                return SkillResult(
                    success=True,
                    result=formatted,
                    metadata={
                        'operation_type': result.operation_type,
                        'result_latex': result.result_latex,
                        'result_pretty': result.result_pretty,
                    }
                )
            else:
                return SkillResult(
                    success=False,
                    error=result.error or "Не удалось вычислить выражение"
                )
        except Exception as e:
            return SkillResult(
                success=False,
                error=f"Ошибка вычисления: {str(e)}"
            )

    def _calculate(self, expression: str) -> MathResult:
        """Вычисляет математическое выражение."""
        expression = self._normalize(expression)
        
        # Пробуем численное вычисление через SymPy
        try:
            expr = sympy.sympify(expression, locals=self._symbols)
            
            # Если есть свободные переменные - алгебраическое выражение
            if expr.free_symbols:
                result = sympy.simplify(expr)
                return MathResult(
                    success=True,
                    result=result,
                    result_latex=sympy.latex(result),
                    result_pretty=sympy.pretty(result),
                    operation_type="algebraic",
                )
            else:
                # Численное вычисление
                result = expr.evalf()
                return MathResult(
                    success=True,
                    result=result,
                    result_latex=sympy.latex(expr),
                    result_pretty=str(result),
                    operation_type="numeric",
                )
        except Exception as e:
            return MathResult(
                success=False,
                result=None,
                error=f"Не удалось вычислить: {e}",
            )

    def _normalize(self, expr: str) -> str:
        """Нормализует выражение."""
        expr = expr.strip()
        replacements = {
            '^': '**',
            '×': '*',
            '÷': '/',
            '−': '-',
            '√': 'sqrt',
            'π': 'pi',
        }
        for old, new in replacements.items():
            expr = expr.replace(old, new)
        return expr

    def _format_result(self, result: MathResult) -> str:
        """Форматирует результат для чата."""
        if not result.success:
            return f"Ошибка: {result.error}"
        
        op_names = {
            'numeric': 'Вычисление',
            'algebraic': 'Алгебра',
        }
        op_name = op_names.get(result.operation_type, 'Результат')
        
        result_value = result.result_pretty or str(result.result)
        return f"**{op_name}**\n\n**Результат:** {result_value}"
