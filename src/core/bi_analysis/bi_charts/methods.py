from django.db import connection
from psycopg2 import sql
from decimal import Decimal
from src.core.bi_analysis.services.services import build_dataset_query

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

def get_rows_for_chart(dataset, chart_fields):
    """
    :param dataset: объект DataSet
    :param chart_fields: список объектов DataSetField (или dict с полями name, aggregation, expression/source_column)
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

    select_exprs = []
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

    # Получаем маппинг полей датасета для получения правильных выражений
    ds_fields_map_full = {f.name: f for f in dataset.fields.all()}
    
    # Получаем базовый запрос датасета
    base_query = build_dataset_query(dataset)
    
    # Строим SELECT с агрегациями для chart_fields
    for field in chart_fields:
        output_name = field.get('name')
        if not output_name:
            continue
        
        # Получаем исходное поле датасета
        ds_field = ds_fields_map_full.get(output_name)
        
        # Определяем выражение для колонки
        if ds_field and ds_field.expression:
            # Используем expression из поля датасета
            col_expr = sql.SQL(ds_field.expression)
        else:
            # Используем имя поля напрямую (поле уже должно быть в SELECT базового запроса)
            col_expr = sql.Identifier(output_name)
        
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
        
        if not is_agg:
            group_by_exprs.append(col_expr)

    # Строим итоговый запрос: SELECT с агрегациями FROM (базовый запрос)
    subquery = sql.SQL('({}) AS dataset_query').format(base_query)
    
    final_query_parts = [
        sql.SQL('SELECT {}').format(sql.SQL(', ').join(select_exprs)),
        sql.SQL('FROM {}').format(subquery)
    ]
    
    if group_by_exprs:
        final_query_parts.append(
            sql.SQL('GROUP BY {}').format(sql.SQL(', ').join(group_by_exprs))
        )
    
    final_query = sql.SQL(' ').join(final_query_parts)

    with connection.cursor() as cursor:
        cursor.execute(final_query)
        columns = [col[0] for col in cursor.description]
        result = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

    return result


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
        column = (
            field.get('expression') or
            field.get('source_column') or
            output_name
        )
        aggregation = field.get('aggregation', 'none')
        agg_expr, is_agg = get_agg_sql(aggregation, column)
        expr = sql.SQL('{} AS {}').format(agg_expr, sql.Identifier(output_name))
        select_exprs.append(expr)
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
        columns = [col[0] for col in cursor.description]
        result = [dict(zip(columns, row)) for row in cursor.fetchall()]

    return result
