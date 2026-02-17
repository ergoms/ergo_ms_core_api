import re
from psycopg2 import sql

ALLOWED_FUNCTIONS = frozenset([
    'SUM', 'AVG', 'COUNT', 'ROUND', 'IF', 'CASE', 'WHEN', 'THEN', 'ELSE', 'END',
    'CONCAT', 'DATE_TRUNC', 'COALESCE', 'NVL', 'CEIL', 'FLOOR', 'SUBSTR',
    'CAST', 'NOW', 'ROW_NUMBER', 'RANK', 'OVER', 'PARTITION', 'BY', 'AS',
    'INTEGER', 'NUMERIC', 'TEXT', 'BOOL', 'DATE', 'TRUE', 'FALSE', 'NULL',
    'ARRAY_LENGTH', 'UNNEST', 'TO_CHAR', 'UCCOUNT', 'MIN', 'MAX'
])
NUMERIC_AGGREGATES = frozenset(['SUM', 'AVG', 'MIN', 'MAX'])

def is_formula(expression):
    if not expression or not isinstance(expression, str):
        return False
    return '[' in expression


def _parse_formula_tokens(expr):
    tokens = []
    i = 0
    n = len(expr)
    while i < n:
        if expr[i] == '[':
            j = i + 1
            while j < n and expr[j] != ']':
                j += 1
            if j < n:
                name = expr[i + 1:j].strip()
                tokens.append(('ref', name, i))
                i = j + 1
                continue
            tokens.append(('op', expr[i], i))
            i += 1
            continue
        if expr[i] in ' \t':
            i += 1
            continue
        if expr[i] in '(),':
            tokens.append(('op', expr[i], i))
            i += 1
            continue
        if expr[i] in '"\'':
            quote = expr[i]
            j = i + 1
            while j < n:
                if expr[j] == '\\':
                    j += 2
                    continue
                if expr[j] == quote:
                    j += 1
                    break
                j += 1
            tokens.append(('string', expr[i:j], i))
            i = j
            continue
        if expr[i].isdigit() or (expr[i] == '.' and i + 1 < n and expr[i + 1].isdigit()):
            j = i
            while j < n and (expr[j].isdigit() or expr[j] == '.'):
                j += 1
            tokens.append(('number', expr[i:j], i))
            i = j
            continue
        if expr[i] in '=<>!':
            j = i
            while j < n and expr[j] in '=<>!':
                j += 1
            op = expr[i:j]
            if op == '<>' or op == '!=' or op == '>=' or op == '<=':
                pass
            tokens.append(('op', op, i))
            i = j
            continue
        if expr[i] in '+*-/':
            tokens.append(('op', expr[i], i))
            i += 1
            continue
        if expr[i].isalpha() or expr[i] in '_':
            j = i
            while j < n and (expr[j].isalnum() or expr[j] in '_'):
                j += 1
            word = expr[i:j]
            tokens.append(('ident', word, i))
            i = j
            continue
        i += 1
    return tokens


def formula_to_sql(expression, field_refs, param_refs=None):
    """
    Преобразует формулу в безопасный SQL-фрагмент.

    :param expression: строка формулы (например, "SUM([Sales]) / COUNT([Id])")
    :param field_refs: dict имя_поля -> sql.Composable (ссылка на колонку)
    :param param_refs: dict имя_параметра -> sql.Composable (литерал), по умолчанию {}
    :return: (sql.Composable, None) при успехе или (None, str) при ошибке
    """
    if param_refs is None:
        param_refs = {}
    tokens = _parse_formula_tokens(expression)
    parts = []
    depth = 0
    pending_numeric_aggregate = False
    wrap_refs_until_depth = None
    for kind, value, pos in tokens:
        if kind == 'op':
            if value == '(':
                depth += 1
                if pending_numeric_aggregate:
                    wrap_refs_until_depth = depth
                    pending_numeric_aggregate = False
            elif value == ')':
                if wrap_refs_until_depth is not None and depth == wrap_refs_until_depth:
                    wrap_refs_until_depth = None
                depth -= 1
        if kind == 'ident':
            pending_numeric_aggregate = value.upper() in NUMERIC_AGGREGATES
        if kind == 'ref':
            if not value.strip():
                return None, "Пустая ссылка []"
            if value in field_refs:
                ref_sql = field_refs[value]
                if wrap_refs_until_depth is not None and depth >= wrap_refs_until_depth:
                    sanitized = sql.SQL(
                        "NULLIF( regexp_replace( replace({}::text, ',', '.'), '[^0-9.\\-]', '', 'g' ), '' )"
                    ).format(ref_sql)
                    parts.append(sql.SQL(
                        "( CASE WHEN {0} ~ '^-?[0-9]+(\\.[0-9]*)?$' THEN {0}::numeric ELSE NULL END )"
                    ).format(sanitized))
                else:
                    parts.append(ref_sql)
            elif value in param_refs:
                parts.append(param_refs[value])
            else:
                return None, f"Неизвестная ссылка: [{value}]"
        elif kind == 'string':
            inner = value[1:-1].replace("\\'", "'").replace('\\"', '"')
            parts.append(sql.Literal(inner))
        elif kind == 'number':
            try:
                if '.' in value:
                    parts.append(sql.Literal(float(value)))
                else:
                    parts.append(sql.Literal(int(value)))
            except ValueError:
                parts.append(sql.SQL(value))
        elif kind == 'ident':
            up = value.upper()
            if up in ALLOWED_FUNCTIONS:
                parts.append(sql.SQL(value))
            else:
                return None, f"Неизвестная функция или идентификатор: {value}"
        elif kind == 'op':
            if value == ' ':
                continue
            safe = value.replace('<', '').replace('>', '').replace('=', '').replace('!', '')
            if not safe or safe in '(),':
                parts.append(sql.SQL(value))
            else:
                for c in value:
                    if c not in '=<>!+-*/%,() ':
                        return None, f"Недопустимый оператор: {value!r}"
                parts.append(sql.SQL(value))
    if not parts:
        return None, "Пустое выражение"
    return sql.SQL('').join(parts), None


