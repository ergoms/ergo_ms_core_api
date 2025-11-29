"""
Безопасный исполнитель математических выражений.
Использует SymPy для символьных вычислений и NumPy для численных.
"""
from __future__ import annotations

import ast
import logging
import operator
from typing import Any, Dict, Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

# Безопасные операторы для eval
SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

# Безопасные математические функции
SAFE_FUNCTIONS = {
    'abs': abs,
    'round': round,
    'min': min,
    'max': max,
    'sum': sum,
    'len': len,
    'int': int,
    'float': float,
    # NumPy функции
    'sqrt': np.sqrt,
    'sin': np.sin,
    'cos': np.cos,
    'tan': np.tan,
    'asin': np.arcsin,
    'acos': np.arccos,
    'atan': np.arctan,
    'atan2': np.arctan2,
    'sinh': np.sinh,
    'cosh': np.cosh,
    'tanh': np.tanh,
    'exp': np.exp,
    'log': np.log,
    'log10': np.log10,
    'log2': np.log2,
    'floor': np.floor,
    'ceil': np.ceil,
    'factorial': lambda n: float(__import__('math').factorial(int(n))),
    'gcd': np.gcd,
    'lcm': np.lcm,
    'degrees': np.degrees,
    'radians': np.radians,
}

# Безопасные константы
SAFE_CONSTANTS = {
    'pi': np.pi,
    'e': np.e,
    'inf': np.inf,
    'nan': np.nan,
    'tau': 2 * np.pi,
}


class SafeMathExecutor:
    """
    Безопасный исполнитель математических выражений.
    Не использует eval/exec напрямую, парсит AST.
    """
    
    def __init__(self) -> None:
        self._functions = SAFE_FUNCTIONS.copy()
        self._constants = SAFE_CONSTANTS.copy()
    
    def evaluate(self, expression: str, variables: Optional[Dict[str, Any]] = None) -> Union[float, complex, np.ndarray]:
        """
        Безопасно вычисляет математическое выражение.
        
        Args:
            expression: Математическое выражение (например: "2 + 2 * 3")
            variables: Словарь переменных (например: {"x": 5, "y": 10})
        
        Returns:
            Результат вычисления
        
        Raises:
            ValueError: При невалидном выражении
            TypeError: При неподдерживаемых операциях
        """
        variables = variables or {}
        
        # Нормализация выражения
        expression = self._normalize_expression(expression)
        
        try:
            tree = ast.parse(expression, mode='eval')
            return self._eval_node(tree.body, variables)
        except SyntaxError as e:
            raise ValueError(f"Синтаксическая ошибка в выражении: {e}")
        except Exception as e:
            raise ValueError(f"Ошибка вычисления: {e}")
    
    def _normalize_expression(self, expr: str) -> str:
        """Нормализует выражение для парсинга."""
        expr = expr.strip()
        # Замена ^ на ** для степени
        expr = expr.replace('^', '**')
        # Замена математических символов
        replacements = {
            '×': '*',
            '÷': '/',
            '−': '-',
            '√': 'sqrt',
            'π': 'pi',
            '²': '**2',
            '³': '**3',
        }
        for old, new in replacements.items():
            expr = expr.replace(old, new)
        return expr
    
    def _eval_node(self, node: ast.AST, variables: Dict[str, Any]) -> Any:
        """Рекурсивно вычисляет AST ноду."""
        if isinstance(node, ast.Constant):
            return node.value
        
        if isinstance(node, ast.Num):  # Для совместимости со старыми версиями Python
            return node.n
        
        if isinstance(node, ast.Name):
            name = node.id
            if name in variables:
                return variables[name]
            if name in self._constants:
                return self._constants[name]
            if name in self._functions:
                return self._functions[name]
            raise ValueError(f"Неизвестная переменная: {name}")
        
        if isinstance(node, ast.BinOp):
            left = self._eval_node(node.left, variables)
            right = self._eval_node(node.right, variables)
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise TypeError(f"Неподдерживаемый оператор: {op_type.__name__}")
            return SAFE_OPERATORS[op_type](left, right)
        
        if isinstance(node, ast.UnaryOp):
            operand = self._eval_node(node.operand, variables)
            op_type = type(node.op)
            if op_type not in SAFE_OPERATORS:
                raise TypeError(f"Неподдерживаемый унарный оператор: {op_type.__name__}")
            return SAFE_OPERATORS[op_type](operand)
        
        if isinstance(node, ast.Call):
            func = self._eval_node(node.func, variables)
            if not callable(func):
                raise TypeError(f"Объект не является функцией")
            args = [self._eval_node(arg, variables) for arg in node.args]
            return func(*args)
        
        if isinstance(node, ast.List):
            return [self._eval_node(elem, variables) for elem in node.elts]
        
        if isinstance(node, ast.Tuple):
            return tuple(self._eval_node(elem, variables) for elem in node.elts)
        
        raise TypeError(f"Неподдерживаемый тип узла: {type(node).__name__}")
    
    def add_variable(self, name: str, value: Any) -> None:
        """Добавляет переменную для использования в выражениях."""
        self._constants[name] = value
    
    def add_function(self, name: str, func) -> None:
        """Добавляет функцию для использования в выражениях."""
        if not callable(func):
            raise TypeError(f"Объект {name} не является вызываемым")
        self._functions[name] = func

