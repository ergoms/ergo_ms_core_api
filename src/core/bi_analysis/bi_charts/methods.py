from django.db import connection
from psycopg2 import sql
from decimal import Decimal

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
    :param dataset: объект DataSet (или строка с именем итоговой таблицы)
    :param chart_fields: список объектов DataSetField (или dict с полями name, aggregation, expression/source_column)
    :return: список словарей (одна строка — одна агрегированная группа)
    """
    # Получаем имя итоговой таблицы
    table_name = getattr(dataset, 'table_name', None) or getattr(dataset, 'table_ref', None) or dataset
    if not isinstance(table_name, str):
        raise ValueError('dataset должен быть объектом с table_name/table_ref или строкой')

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
        new_field = dict(field)
        new_field['aggregation'] = aggregation or 'none'
        enriched_fields.append(new_field)
    chart_fields = enriched_fields
    # --------------------------------------------------------------------------

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
        output_name = getattr(field, 'name', None) or field.get('name')
        column = (
            getattr(field, 'expression', None)
            or getattr(field, 'source_column', None)
            or field.get('expression')
            or field.get('source_column')
            or output_name
        )
        aggregation = getattr(field, 'aggregation', None) or field.get('aggregation', 'none')

        agg_expr, is_agg = get_agg_sql(aggregation, column)
        expr = sql.SQL('{} AS {}').format(
            agg_expr,
            sql.Identifier(output_name)
        )
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

    with connection.cursor() as cursor:
        cursor.execute(query)
        columns = [col[0] for col in cursor.description]
        result = [
            dict(zip(columns, row))
            for row in cursor.fetchall()
        ]

    return result
