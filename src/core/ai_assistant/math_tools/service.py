"""
Сервис математических вычислений с использованием SymPy.
Поддерживает символьные и численные вычисления.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union

import numpy as np

from .parser import MathExpressionParser, MathOperationType, ParsedMathExpression
from .safe_executor import SafeMathExecutor

logger = logging.getLogger(__name__)

# Ленивый импорт SymPy для ускорения загрузки
_sympy = None


def _get_sympy():
    """Ленивая загрузка SymPy."""
    global _sympy
    if _sympy is None:
        import sympy
        _sympy = sympy
    return _sympy


@dataclass
class MathResult:
    """Результат математического вычисления."""
    success: bool
    result: Any
    result_latex: Optional[str] = None
    result_pretty: Optional[str] = None
    steps: Optional[List[str]] = None
    error: Optional[str] = None
    operation_type: Optional[str] = None


class MathToolsService:
    """
    Сервис для математических вычислений.
    Использует SymPy для символьной математики и NumPy для численных.
    """
    
    def __init__(self) -> None:
        self._parser = MathExpressionParser()
        self._safe_executor = SafeMathExecutor()
        self._sympy_initialized = False
    
    def _init_sympy(self) -> None:
        """Инициализирует SymPy символы."""
        if self._sympy_initialized:
            return
        
        sympy = _get_sympy()
        # Создаем часто используемые символы
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
        self._sympy_initialized = True
    
    def calculate(self, query: str, use_llm_parsing: bool = False) -> MathResult:
        """
        Главная точка входа для математических вычислений.
        
        Args:
            query: Математический запрос на естественном языке или выражение
            use_llm_parsing: Использовать ли LLM для парсинга (требует внешний вызов)
        
        Returns:
            MathResult с результатом вычисления
        """
        try:
            # Парсим запрос
            parsed = self._parser.parse(query)
            
            # Выбираем метод вычисления
            handlers = {
                MathOperationType.ARITHMETIC: self._calculate_arithmetic,
                MathOperationType.ALGEBRA: self._calculate_algebra,
                MathOperationType.CALCULUS_DERIVATIVE: self._calculate_derivative,
                MathOperationType.CALCULUS_INTEGRAL: self._calculate_integral,
                MathOperationType.LIMIT: self._calculate_limit,
                MathOperationType.SIMPLIFY: self._simplify,
                MathOperationType.EXPAND: self._expand,
                MathOperationType.FACTOR: self._factor,
                MathOperationType.SOLVE: self._solve,
                MathOperationType.STATISTICS: self._calculate_statistics,
            }
            
            handler = handlers.get(parsed.operation_type, self._try_generic_calculation)
            return handler(parsed)
            
        except Exception as e:
            logger.exception("Ошибка математического вычисления")
            return MathResult(
                success=False,
                result=None,
                error=str(e),
            )
    
    def _calculate_arithmetic(self, parsed: ParsedMathExpression) -> MathResult:
        """Вычисляет простое арифметическое выражение."""
        try:
            result = self._safe_executor.evaluate(parsed.expression)
            return MathResult(
                success=True,
                result=result,
                result_pretty=str(result),
                operation_type="arithmetic",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _calculate_algebra(self, parsed: ParsedMathExpression) -> MathResult:
        """Вычисляет алгебраическое выражение через SymPy."""
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            result = sympy.simplify(expr)
            
            return MathResult(
                success=True,
                result=result,
                result_latex=sympy.latex(result),
                result_pretty=sympy.pretty(result),
                operation_type="algebra",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _calculate_derivative(self, parsed: ParsedMathExpression) -> MathResult:
        """Вычисляет производную."""
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            var_name = parsed.variables.get('variable', 'x')
            var = self._symbols.get(var_name, sympy.Symbol(var_name))
            
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            derivative = sympy.diff(expr, var)
            simplified = sympy.simplify(derivative)
            
            steps = [
                f"Исходное выражение: {sympy.pretty(expr)}",
                f"Берём производную по {var_name}",
                f"Результат: {sympy.pretty(simplified)}",
            ]
            
            return MathResult(
                success=True,
                result=simplified,
                result_latex=sympy.latex(simplified),
                result_pretty=sympy.pretty(simplified),
                steps=steps,
                operation_type="derivative",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _calculate_integral(self, parsed: ParsedMathExpression) -> MathResult:
        """Вычисляет интеграл."""
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            var_name = parsed.variables.get('variable', 'x')
            var = self._symbols.get(var_name, sympy.Symbol(var_name))
            
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            integral = sympy.integrate(expr, var)
            
            steps = [
                f"Исходное выражение: {sympy.pretty(expr)}",
                f"Интегрируем по {var_name}",
                f"Результат: {sympy.pretty(integral)} + C",
            ]
            
            return MathResult(
                success=True,
                result=integral,
                result_latex=sympy.latex(integral) + " + C",
                result_pretty=sympy.pretty(integral) + " + C",
                steps=steps,
                operation_type="integral",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _calculate_limit(self, parsed: ParsedMathExpression) -> MathResult:
        """Вычисляет предел."""
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            var_name = parsed.variables.get('variable', 'x')
            point_str = parsed.variables.get('point', '0')
            var = self._symbols.get(var_name, sympy.Symbol(var_name))
            
            # Парсим точку
            if point_str.lower() in ('inf', 'infinity', '∞'):
                point = sympy.oo
            elif point_str.lower() in ('-inf', '-infinity', '-∞'):
                point = -sympy.oo
            else:
                point = sympy.sympify(point_str)
            
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            limit_result = sympy.limit(expr, var, point)
            
            steps = [
                f"Исходное выражение: {sympy.pretty(expr)}",
                f"Находим предел при {var_name} → {point_str}",
                f"Результат: {sympy.pretty(limit_result)}",
            ]
            
            return MathResult(
                success=True,
                result=limit_result,
                result_latex=sympy.latex(limit_result),
                result_pretty=sympy.pretty(limit_result),
                steps=steps,
                operation_type="limit",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _simplify(self, parsed: ParsedMathExpression) -> MathResult:
        """Упрощает выражение."""
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            simplified = sympy.simplify(expr)
            
            return MathResult(
                success=True,
                result=simplified,
                result_latex=sympy.latex(simplified),
                result_pretty=sympy.pretty(simplified),
                operation_type="simplify",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _expand(self, parsed: ParsedMathExpression) -> MathResult:
        """Раскрывает скобки."""
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            expanded = sympy.expand(expr)
            
            return MathResult(
                success=True,
                result=expanded,
                result_latex=sympy.latex(expanded),
                result_pretty=sympy.pretty(expanded),
                operation_type="expand",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _factor(self, parsed: ParsedMathExpression) -> MathResult:
        """Факторизует выражение."""
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            factored = sympy.factor(expr)
            
            return MathResult(
                success=True,
                result=factored,
                result_latex=sympy.latex(factored),
                result_pretty=sympy.pretty(factored),
                operation_type="factor",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _solve(self, parsed: ParsedMathExpression) -> MathResult:
        """Решает уравнение."""
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            
            # Определяем переменные в выражении
            free_symbols = expr.free_symbols
            if free_symbols:
                var = list(free_symbols)[0]  # Берём первую свободную переменную
            else:
                var = self._symbols['x']
            
            solutions = sympy.solve(expr, var)
            
            if isinstance(solutions, list):
                solutions_str = [str(s) for s in solutions]
                result_pretty = f"{var} = " + " или ".join(solutions_str)
            else:
                result_pretty = f"{var} = {solutions}"
            
            steps = [
                f"Уравнение: {sympy.pretty(expr)} = 0",
                f"Решаем относительно {var}",
                f"Корни: {result_pretty}",
            ]
            
            return MathResult(
                success=True,
                result=solutions,
                result_latex=sympy.latex(solutions) if hasattr(solutions, '__iter__') else sympy.latex(solutions),
                result_pretty=result_pretty,
                steps=steps,
                operation_type="solve",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _calculate_statistics(self, parsed: ParsedMathExpression) -> MathResult:
        """Вычисляет статистику."""
        try:
            # Пробуем извлечь числа из выражения
            import re
            numbers = re.findall(r'-?\d+\.?\d*', parsed.expression)
            data = [float(n) for n in numbers]
            
            if not data:
                return MathResult(success=False, result=None, error="Не найдены числа для статистики")
            
            arr = np.array(data)
            stats = {
                'mean': float(np.mean(arr)),
                'median': float(np.median(arr)),
                'std': float(np.std(arr)),
                'var': float(np.var(arr)),
                'min': float(np.min(arr)),
                'max': float(np.max(arr)),
                'sum': float(np.sum(arr)),
                'count': len(arr),
            }
            
            result_pretty = (
                f"Среднее: {stats['mean']:.4f}\n"
                f"Медиана: {stats['median']:.4f}\n"
                f"Стд. отклонение: {stats['std']:.4f}\n"
                f"Дисперсия: {stats['var']:.4f}\n"
                f"Мин: {stats['min']}, Макс: {stats['max']}\n"
                f"Сумма: {stats['sum']}, Количество: {stats['count']}"
            )
            
            return MathResult(
                success=True,
                result=stats,
                result_pretty=result_pretty,
                operation_type="statistics",
            )
        except Exception as e:
            return MathResult(success=False, result=None, error=str(e))
    
    def _try_generic_calculation(self, parsed: ParsedMathExpression) -> MathResult:
        """Пробует выполнить общее вычисление."""
        # Сначала пробуем безопасный executor
        try:
            result = self._safe_executor.evaluate(parsed.expression)
            return MathResult(
                success=True,
                result=result,
                result_pretty=str(result),
                operation_type="numeric",
            )
        except Exception:
            pass
        
        # Затем пробуем SymPy
        self._init_sympy()
        sympy = _get_sympy()
        
        try:
            expr = sympy.sympify(parsed.expression, locals=self._symbols)
            # Пробуем численно вычислить
            result = expr.evalf()
            
            return MathResult(
                success=True,
                result=result,
                result_latex=sympy.latex(expr),
                result_pretty=sympy.pretty(expr),
                operation_type="symbolic",
            )
        except Exception as e:
            return MathResult(
                success=False,
                result=None,
                error=f"Не удалось вычислить выражение: {e}",
            )
    
    def is_math_query(self, text: str) -> bool:
        """Проверяет, является ли запрос математическим."""
        return self._parser.is_math_query(text)
    
    def format_result_for_chat(self, result: MathResult) -> str:
        """Форматирует результат для отображения в чате."""
        if not result.success:
            return f"Ошибка: {result.error}"
        
        parts = []
        
        if result.operation_type:
            op_names = {
                'arithmetic': 'Арифметика',
                'algebra': 'Алгебра',
                'derivative': 'Производная',
                'integral': 'Интеграл',
                'limit': 'Предел',
                'simplify': 'Упрощение',
                'expand': 'Раскрытие скобок',
                'factor': 'Факторизация',
                'solve': 'Решение уравнения',
                'statistics': 'Статистика',
                'numeric': 'Численное вычисление',
                'symbolic': 'Символьное вычисление',
            }
            op_name = op_names.get(result.operation_type, result.operation_type)
            parts.append(f"**{op_name}**")
        
        if result.steps:
            parts.append("\n**Шаги решения:**")
            for i, step in enumerate(result.steps, 1):
                parts.append(f"{i}. {step}")
        
        # Форматируем результат
        result_value = result.result_pretty or str(result.result) if result.result is not None else None
        if result_value:
            # Для многострочных результатов используем блок кода
            if '\n' in str(result_value):
                parts.append(f"\n**Результат:**\n```\n{result_value}\n```")
            else:
                # Для простых результатов - inline
                parts.append(f"\n**Результат:** {result_value}")
        
        return "\n".join(parts)

