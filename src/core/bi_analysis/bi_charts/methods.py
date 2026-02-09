import re
from django.db import connection
from psycopg2 import sql
from decimal import Decimal
from src.core.bi_analysis.services.services import build_dataset_query, read_file_to_dataframe

PG_NUMERIC = {
    'smallint', 'integer', 'bigint',
    'decimal', 'numeric', 'real', 'double precision'
}
PG_DATE = {'date', 'timestamp', 'timestamp without time zone',
           'timestamp with time zone', 'time', 'time without time zone'}

SAMPLE = 100

def _probe_type(table: str, column: str) -> str:
    patt_num  = r'^[0-9]+(\.[0-9]+)?$'
    patt_date = r'^[0-9]{4}-[0-9]{2}-[0-9]{2}$|^[0-9]{2}\.[0-9]{2}\.[0-9]{4}$'

    with connection.cursor() as cur:
        # 1) numeric?
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {} WHERE {} !~ %s LIMIT %s")
               .format(sql.Identifier(table), sql.Identifier(column)),
            [patt_num, SAMPLE]
        )
        if cur.fetchone()[0] == 0:
            return 'number'

        # 2) date?
        cur.execute(
            sql.SQL("SELECT COUNT(*) FROM {} WHERE {} !~ %s LIMIT %s")
               .format(sql.Identifier(table), sql.Identifier(column)),
            [patt_date, SAMPLE]
        )
        if cur.fetchone()[0] == 0:
            return 'date'

    return 'string'

def _resolve_column_index(columns, col_name, field_order=None, ordered_names=None):
    """Возвращает индекс колонки по имени (точное совпадение, strip, order поля или порядок в датасете)."""
    if not columns:
        return None
    if col_name in columns:
        return columns.index(col_name)
    col_stripped = str(col_name or '').strip()
    for i, c in enumerate(columns):
        if str(c or '').strip() == col_stripped:
            return i
    if field_order is not None and 0 <= field_order < len(columns):
        return field_order
    if ordered_names and col_name in ordered_names and len(ordered_names) <= len(columns):
        return ordered_names.index(col_name)
    return None


def _row_passes_filters(row, filter_conditions, columns, name_to_idx):
    """Проверяет, проходит ли строка (list) все условия фильтра. name_to_idx: имя поля -> индекс колонки."""
    if not filter_conditions or not name_to_idx:
        return True
    for fc in filter_conditions:
        name = fc.get('name') or (fc.get('field') or {}).get('name')
        if not name:
            continue
        col_idx = name_to_idx.get(name)
        if col_idx is None or col_idx >= len(row):
            continue
        filt = fc.get('filter') or fc
        op = (filt.get('op') or 'eq').lower()
        value = filt.get('value')
        cell = row[col_idx]
        cell_str = str(cell).strip() if cell is not None else ''
        if op == 'eq':
            if not (cell == value or cell_str == str(value).strip()):
                return False
        elif op == 'neq':
            if cell == value or cell_str == str(value).strip():
                return False
        elif op == 'in':
            vals = value if isinstance(value, (list, tuple)) else [value]
            if vals and cell not in vals and cell_str not in [str(v).strip() for v in vals]:
                return False
        elif op == 'nin':
            vals = value if isinstance(value, (list, tuple)) else [value]
            if vals and (cell in vals or cell_str in [str(v).strip() for v in vals]):
                return False
        elif op in ('gt', 'gte', 'lt', 'lte'):
            try:
                cv = float(str(cell).replace(',', '.')) if cell not in (None, '') else None
                vv = float(value) if value not in (None, '') else None
                if cv is None or vv is None:
                    return False
                if op == 'gt' and not (cv > vv):
                    return False
                if op == 'gte' and not (cv >= vv):
                    return False
                if op == 'lt' and not (cv < vv):
                    return False
                if op == 'lte' and not (cv <= vv):
                    return False
            except (TypeError, ValueError):
                return False
        elif op in ('contains', 'contains_i'):
            if value is None or (cell_str.upper().find(str(value).upper()) < 0):
                return False
        elif op in ('startswith', 'startswith_i'):
            if value is None or not cell_str.upper().startswith(str(value).upper()):
                return False
        elif op == 'empty':
            if cell is not None and cell_str != '':
                return False
        elif op == 'nempty':
            if cell is None or cell_str == '':
                return False
    return True


def _build_filter_where(filter_conditions, name_to_out):
    """Строит SQL WHERE из условий фильтров (для подзапроса с колонками out_0, out_1, ...)."""
    if not filter_conditions or not name_to_out:
        return None
    where_parts = []
    for fc in filter_conditions:
        name = fc.get('name') or (fc.get('field') or {}).get('name')
        if not name:
            continue
        col_ref = name_to_out.get(name)
        if col_ref is None:
            continue
        filt = fc.get('filter') or fc
        op = (filt.get('op') or 'eq').lower()
        value = filt.get('value')
        col_expr = sql.Identifier(col_ref)
        if op == 'eq':
            where_parts.append(sql.SQL('{} = {}').format(col_expr, sql.Literal(value)))
        elif op == 'neq':
            where_parts.append(sql.SQL('{} IS DISTINCT FROM {}').format(col_expr, sql.Literal(value)))
        elif op == 'in':
            vals = value if isinstance(value, (list, tuple)) else [value]
            if vals:
                where_parts.append(
                    sql.SQL('{} IN ({})').format(col_expr, sql.SQL(',').join(sql.Literal(v) for v in vals))
                )
        elif op == 'nin':
            vals = value if isinstance(value, (list, tuple)) else [value]
            if vals:
                where_parts.append(
                    sql.SQL('{} NOT IN ({})').format(col_expr, sql.SQL(',').join(sql.Literal(v) for v in vals))
                )
        elif op in ('gt', 'gte', 'lt', 'lte'):
            where_parts.append(
                sql.SQL('{} {} {}').format(col_expr, sql.SQL(op), sql.Literal(value))
            )
        elif op in ('contains', 'contains_i'):
            pattern = f'%{value}%' if value is not None else '%%'
            expr = sql.SQL('{}::text ILIKE {}').format(col_expr, sql.Literal(pattern))
            where_parts.append(expr)
        elif op in ('startswith', 'startswith_i'):
            pattern = f'{value}%' if value is not None else '%'
            where_parts.append(sql.SQL('{}::text ILIKE {}').format(col_expr, sql.Literal(pattern)))
        elif op == 'empty':
            where_parts.append(sql.SQL('{} IS NULL OR {}::text = \'\'').format(col_expr, col_expr))
        elif op == 'nempty':
            where_parts.append(sql.SQL('{} IS NOT NULL AND {}::text <> \'\'').format(col_expr, col_expr))
    if not where_parts:
        return None
    return sql.SQL(' AND ').join(where_parts)


def get_rows_for_chart(dataset, chart_fields, filter_conditions=None):
    """
    :param dataset: объект DataSet
    :param chart_fields: список объектов DataSetField (или dict с полями name, aggregation, expression/source_column)
    :param filter_conditions: список dict с name/field, filter{op, value} — применяются как WHERE, не в GROUP BY
    :return: список словарей (одна строка — одна агрегированная группа)
    """
    # Проверяем, что dataset - это объект Dataset с метаданными
    if not hasattr(dataset, 'tables'):
        # Fallback для старых датасетов, которые могут использовать table_ref
        table_name = getattr(dataset, 'table_name', None) or getattr(dataset, 'table_ref', None) or dataset
        if isinstance(table_name, str):
            return _get_rows_for_chart_legacy(dataset, chart_fields, table_name)
        else:
            raise ValueError('dataset должен быть объектом Dataset или строкой с именем таблицы')

    # --------- ДОПОЛНЯЕМ aggregation из DataSetField, если не указано ---------
    ds_fields_map = {}
    if hasattr(dataset, 'fields'):
        ds_fields_map = {f.name: f for f in dataset.fields.all()}
    
    enriched_fields = []
    for field in chart_fields:
        name = getattr(field, 'name', None) or field.get('name')
        aggregation = (
            getattr(field, 'aggregation', None) or
            field.get('aggregation')
        )
        # Если не задана агрегация — ищем дефолтную из DataSetField
        if not aggregation and name in ds_fields_map:
            aggregation = getattr(ds_fields_map[name], 'aggregation', None)
        # Если всё ещё нет, то ставим 'none'
        new_field = dict(field) if not isinstance(field, dict) else field.copy()
        if not isinstance(new_field, dict):
            new_field = {'name': name}
        new_field['aggregation'] = aggregation or 'none'
        enriched_fields.append(new_field)
    chart_fields = enriched_fields
    # --------------------------------------------------------------------------

    main_table = dataset.tables.filter(joined_on_type__isnull=True).first()
    has_joins = dataset.tables.filter(joined_on_type__isnull=False).exists()
    ds_fields_map_full = {f.name: f for f in dataset.fields.all()}

    if (
        main_table
        and main_table.file_upload_id
        and not has_joins
        and len(chart_fields) == 1
    ):
        f = chart_fields[0]
        output_name = f.get('name')
        agg = (f.get('aggregation') or 'none').lower()
        if agg == 'none' and output_name and output_name in ds_fields_map_full:
            ds_agg = getattr(ds_fields_map_full[output_name], 'aggregation', None)
            if ds_agg:
                agg = (ds_agg or 'none').lower()
        if agg == 'none' and output_name:
            agg = 'sum'
        if agg in ('sum', 'avg', 'count') and output_name:
            ds_field = ds_fields_map_full.get(output_name)
            col_name = (getattr(ds_field, 'source_column', None) or output_name) if ds_field else output_name
            try:
                table_data = read_file_to_dataframe(
                    main_table.file_upload_id,
                    sheet_name=getattr(main_table, 'sheet_name', None),
                    row_limit=None
                )
            except Exception:
                table_data = None
            if table_data and table_data.columns:
                ordered_names = list(
                    dataset.fields.all().order_by('order').values_list('name', flat=True)
                )
                field_order = getattr(ds_field, 'order', None) if ds_field else None
                idx = _resolve_column_index(
                    table_data.columns, col_name,
                    field_order=field_order,
                    ordered_names=ordered_names if len(ordered_names) <= len(table_data.columns) else None
                )
                if idx is not None:
                    name_to_idx = {}
                    for field in dataset.fields.all():
                        fc_name = getattr(field, 'source_column', None) or field.name
                        fi = _resolve_column_index(table_data.columns, fc_name)
                        if fi is not None:
                            name_to_idx[field.name] = fi
                    total = 0
                    count = 0
                    for row in table_data.rows:
                        if filter_conditions and not _row_passes_filters(
                            row, filter_conditions, table_data.columns, name_to_idx
                        ):
                            continue
                        if idx >= len(row):
                            continue
                        v = row[idx]
                        s = str(v).replace(',', '.') if v is not None else ''
                        s = re.sub(r'[^0-9.-]', '', s)
                        if s and s != '-':
                            try:
                                total += float(s)
                                count += 1
                            except ValueError:
                                pass
                    result = (
                        [{output_name: total}] if agg == 'sum' else
                        [{output_name: total / count if count else None}] if agg == 'avg' else
                        [{output_name: count}]
                    )
                    return result

    select_exprs = []
    output_names = []  # имена полей, которые реально попали в SELECT (в нужном порядке)
    group_by_exprs = []

    def get_agg_sql(agg, col_expr):
        """col_expr - это уже SQL выражение для колонки"""
        if agg is None or agg.lower() == 'none':
            return col_expr, False

        agg_l = agg.lower()

        if agg_l == 'count':
            return sql.SQL('COUNT({})').format(col_expr), True

        elif agg_l == 'ucount':
            return sql.SQL('COUNT(DISTINCT {})').format(col_expr), True

        elif agg_l == 'sum':
            return sql.SQL(
                "SUM( NULLIF( "
                "       regexp_replace( "
                "           replace({}::text, ',', '.'), "
                "           '[^0-9\\.-]', '', 'g' "
                "       ), "
                "       '' "
                "   )::numeric )"
            ).format(col_expr), True

        elif agg_l == 'avg':
            return sql.SQL('AVG({})').format(col_expr), True

        elif agg_l == 'max':
            return sql.SQL('MAX({})').format(col_expr), True

        elif agg_l == 'min':
            return sql.SQL('MIN({})').format(col_expr), True

        else:
            return col_expr, False

    base_query, display_columns = build_dataset_query(dataset)
    # Базовый запрос возвращает колонки out_0, out_1, ...; display_columns — порядок имён полей
    name_to_out = {name: f'out_{i}' for i, name in enumerate(display_columns)} if display_columns else {}

    for field in chart_fields:
        output_name = field.get('name')
        if not output_name:
            continue

        ds_field = ds_fields_map_full.get(output_name)

        if ds_field and ds_field.expression:
            col_expr = sql.SQL(ds_field.expression)
        else:
            col_expr = sql.Identifier(name_to_out.get(output_name, output_name))
        
        # Получаем агрегацию
        aggregation = field.get('aggregation', 'none')
        
        # Применяем агрегацию
        agg_expr, is_agg = get_agg_sql(aggregation, col_expr)
        
        select_exprs.append(
            sql.SQL('{} AS {}').format(
                agg_expr,
                sql.Identifier(output_name)
            )
        )
        output_names.append(output_name)
        
        if not is_agg:
            group_by_exprs.append(col_expr)

    # Строим итоговый запрос: SELECT с агрегациями FROM (базовый запрос) [WHERE по фильтрам]
    subquery = sql.SQL('({}) AS dataset_query').format(base_query)
    
    final_query_parts = [
        sql.SQL('SELECT {}').format(sql.SQL(', ').join(select_exprs)),
        sql.SQL('FROM {}').format(subquery)
    ]
    
    filter_where = _build_filter_where(filter_conditions or [], name_to_out)
    if filter_where is not None:
        final_query_parts.append(sql.SQL('WHERE {}').format(filter_where))
    
    if group_by_exprs:
        final_query_parts.append(
            sql.SQL('GROUP BY {}').format(sql.SQL(', ').join(group_by_exprs))
        )
    
    final_query = sql.SQL(' ').join(final_query_parts)

    with connection.cursor() as cursor:
        cursor.execute(final_query)
        rows = cursor.fetchall()

    # Важно: возвращаем ключи ровно с именами полей датасета (output_names),
    # а не с потенциально усечёнными alias из PostgreSQL (ограничение 63 байта).
    # Это гарантирует совпадение с f.name на фронте даже для очень длинных имён.
    return [
        dict(zip(output_names, row))
        for row in rows
    ]


def _get_rows_for_chart_legacy(dataset, chart_fields, table_name):
    """Старая реализация для обратной совместимости с table_ref"""
    ds_fields_map = {}
    if hasattr(dataset, 'fields'):
        ds_fields_map = {f.name: f for f in dataset.fields.all()}
    
    enriched_fields = []
    for field in chart_fields:
        name = getattr(field, 'name', None) or field.get('name')
        aggregation = (
            getattr(field, 'aggregation', None) or
            field.get('aggregation')
        )
        if not aggregation and name in ds_fields_map:
            aggregation = getattr(ds_fields_map[name], 'aggregation', None)
        new_field = dict(field) if not isinstance(field, dict) else field.copy()
        if not isinstance(new_field, dict):
            new_field = {'name': name}
        new_field['aggregation'] = aggregation or 'none'
        enriched_fields.append(new_field)
    chart_fields = enriched_fields

    select_exprs = []
    output_names = []
    group_by_exprs = []

    def get_agg_sql(agg, col):
        if agg is None or agg.lower() == 'none':
            return sql.Identifier(col), False
        agg_l = agg.lower()
        if agg_l == 'count':
            return sql.SQL('COUNT({col})').format(col=sql.Identifier(col)), True
        elif agg_l == 'ucount':
            return sql.SQL('COUNT(DISTINCT {col})').format(col=sql.Identifier(col)), True
        elif agg_l == 'sum':
            return sql.SQL(
                "SUM( NULLIF( "
                "       regexp_replace( "
                "           replace({col}::text, ',', '.'), "
                "           '[^0-9\\.-]', '', 'g' "
                "       ), "
                "       '' "
                "   )::numeric )"
            ).format(col=sql.Identifier(col)), True
        elif agg_l == 'avg':
            return sql.SQL('AVG({col})').format(col=sql.Identifier(col)), True
        else:
            return sql.Identifier(col), False

    for field in chart_fields:
        output_name = field.get('name')
        if not output_name:
            continue
        column = (
            field.get('expression') or
            field.get('source_column') or
            output_name
        )
        aggregation = field.get('aggregation', 'none')
        agg_expr, is_agg = get_agg_sql(aggregation, column)
        expr = sql.SQL('{} AS {}').format(agg_expr, sql.Identifier(output_name))
        select_exprs.append(expr)
        output_names.append(output_name)
        if not is_agg:
            group_by_exprs.append(sql.Identifier(column))

    query = sql.SQL('SELECT {} FROM {}').format(
        sql.SQL(', ').join(select_exprs),
        sql.Identifier(table_name)
    )
    if group_by_exprs:
        query += sql.SQL(' GROUP BY {}').format(
            sql.SQL(', ').join(group_by_exprs)
        )
    
    # Добавляем сортировку по первому полю без агрегации (обычно это ось X)
    # Это важно для анализа графиков AI-ассистентом
    if group_by_exprs:
        # Сортируем по первому полю в GROUP BY (обычно ось X)
        query += sql.SQL(' ORDER BY {}').format(group_by_exprs[0])
    elif chart_fields:
        # Если нет группировки, сортируем по первому полю
        first_field_name = getattr(chart_fields[0], 'name', None) or chart_fields[0].get('name')
        query += sql.SQL(' ORDER BY {}').format(sql.Identifier(first_field_name))

    with connection.cursor() as cursor:
        cursor.execute(query)
        rows = cursor.fetchall()

    return [
        dict(zip(output_names, row))
        for row in rows
    ]
