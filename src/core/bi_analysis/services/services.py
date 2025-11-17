import csv
from uuid import uuid4
from django.db import connection, transaction, models
from rest_framework.exceptions import ValidationError
import pandas as pd
from psycopg2 import sql

from src.core.bi_analysis.bi_datasets.models import DataSetField, DataSetTable, FileUpload

def populate_initial_fields(dataset, temp_table_name, staging_table=None):
    """
    Создаёт DataSetField для каждой колонки temp_table_name с дефолтными type/aggregation.
    Если имя столбца вида <table>__<col> — ищет соответствующую DataSetTable.
    УСТАРЕВШАЯ ФУНКЦИЯ - используется только для обратной совместимости.
    """
    cols = introspect_columns(temp_table_name)
    ds_tables = {t.table_name: t for t in DataSetTable.objects.filter(dataset=dataset)}
    objs = []

    for idx, col in enumerate(cols):
        source_tbl = None
        if '__' in col:
            tbl_name, _ = col.split('__', 1)
            source_tbl = ds_tables.get(tbl_name)
        else:
            if staging_table:
                tbl_name = staging_table.table_name if hasattr(staging_table, 'table_name') else staging_table
                source_tbl = ds_tables.get(tbl_name)
            if not source_tbl:
                source_tbl = next(iter(ds_tables.values()), None)

        if not source_tbl:
            print(f"[WARNING] Не удалось найти source_table для колонки '{col}'")
            continue

        objs.append(DataSetField(
            dataset=dataset,
            name=col,
            source_table=source_tbl,
            source_column=col,
            order=idx
        ))
    DataSetField.objects.bulk_create(objs)


def populate_initial_fields_from_file(dataset, file_upload, source_table):
    """
    Создаёт DataSetField для каждой колонки из файла без создания таблицы в БД.
    Читает файл напрямую через pandas для получения списка колонок.
    """
    try:
        df = read_file_to_dataframe(file_upload.id)
        cols = list(df.columns.astype(str))
    except Exception as e:
        # Fallback: используем columns_info если есть
        if file_upload.columns_info and 'columns' in file_upload.columns_info:
            cols = file_upload.columns_info['columns']
        else:
            raise ValidationError(f"Не удалось прочитать колонки из файла: {str(e)}")
    
    objs = []
    for idx, col in enumerate(cols):
        objs.append(DataSetField(
            dataset=dataset,
            name=col,
            source_table=source_table,
            source_column=col,
            order=idx
        ))
    
    if objs:
        DataSetField.objects.bulk_create(objs)

def create_temp_table_from_source(dataset):
    """
    УСТАРЕВШАЯ ФУНКЦИЯ - больше не создает temp таблицы.
    Оставлена для обратной совместимости.
    """
    print(f"[WARNING] create_temp_table_from_source вызвана - функция устарела")
    raise ValidationError("Создание temp таблиц больше не поддерживается. Используйте новую архитектуру с чтением файлов напрямую.")

def find_existing_temp_table_for_file(file_upload_id):
    """
    Ищет существующую staging таблицу для данного файла.
    Проверяет таблицы через DataSetTable и также все staging_ таблицы с нужными колонками.
    """
    try:
        upload = FileUpload.objects.get(pk=file_upload_id)
        
        # Сначала проверяем через DataSetTable
        existing_tables = DataSetTable.objects.filter(file_upload_id=file_upload_id)
        for ds_table in existing_tables:
            # Ищем staging или temp таблицы (temp для обратной совместимости)
            if ds_table.table_name.startswith(('staging_', 'temp_')):
                if table_exists(ds_table.table_name):
                    return ds_table.table_name
        
        # Если не нашли через DataSetTable, проверяем все staging_ таблицы
        # Загружаем ожидаемые колонки из файла для сравнения
        cols_from_file = []
        if upload.file_type == 'xlsx':
            df = pd.read_excel(upload.file.path, header=0, nrows=0)
            cols_from_file = list(df.columns.astype(str))
        elif upload.file_type in ('csv', 'txt'):
            with open(upload.file.path, 'r', encoding='cp1251', errors='replace', newline='') as f:
                reader = csv.reader(f)
                cols_from_file = next(reader, [])
        
        if cols_from_file:
            # Ищем все staging_ таблицы с таким же набором колонок
            # Также проверяем temp_ для обратной совместимости
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT tablename 
                    FROM pg_tables 
                    WHERE schemaname = 'public' 
                    AND (tablename LIKE 'staging_%' OR tablename LIKE 'temp_%')
                """)
                staging_tables = [row[0] for row in cursor.fetchall()]
                
                for staging_table in staging_tables:
                    try:
                        existing_cols = introspect_columns(staging_table)
                        # Сравниваем наборы колонок
                        if set(existing_cols) == set(cols_from_file):
                            return staging_table
                    except:
                        continue
    except Exception as e:
        print(f"[FIND STAGING TABLE] Error: {e}")
    
    return None

def import_file_upload_to_table(file_upload_id, dataset=None, reuse_existing=True):
    """
    УСТАРЕВШАЯ ФУНКЦИЯ - больше не создает таблицы в БД.
    Оставлена для обратной совместимости со старым кодом.
    
    НОВАЯ АРХИТЕКТУРА: данные читаются напрямую из файлов через pandas
    без создания материализованных таблиц.
    
    Эта функция больше не должна вызываться в новом коде.
    Используйте read_file_to_dataframe() вместо этого.
    """
    # Не создаем таблицы - это устаревший подход
    # Возвращаем None или пустую строку для обратной совместимости
    print(f"[WARNING] import_file_upload_to_table вызвана для file_id={file_upload_id} - функция устарела")
    return None


def _create_table_and_load(staging, cols, rows):
    """
    Общая логика: создаём staging-таблицу TEXT и массово вставляем rows.
    """
    col_defs = ", ".join(f'"{c}" TEXT' for c in cols)

    placeholders = ", ".join(["%s"] * len(cols))
    insert_sql   = f'''
        INSERT INTO "{staging}" ({", ".join(f'"{c}"' for c in cols)})
        VALUES ({placeholders})
    '''

    with connection.cursor() as cursor:
        cursor.execute(f'CREATE TABLE "{staging}" ({col_defs});')
        cursor.executemany(insert_sql, rows)

    return staging

def introspect_columns(temp_table_name):
    """
    Возвращает список (column_name, data_type) для временной таблицы.
    """
    safe_name = temp_table_name.replace('"', '""')
    sql = f'SELECT * FROM "{safe_name}" LIMIT 0;'
    with connection.cursor() as cursor:
        cursor.execute(sql)
        return [col[0] for col in cursor.description]
    
def table_exists(table_name):
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s)", [table_name])
        exists = cursor.fetchone()[0] is not None
        print(f"[TABLE EXISTS] {table_name}: {exists}")
        return exists
    
def safe_drop_table(table_name):
    """
    Безопасно удаляет таблицу, если она есть.
    """
    with connection.cursor() as cursor:
        cursor.execute(f'DROP TABLE IF EXISTS "{table_name}" CASCADE;')

def auto_join_table(dataset, table, left_column, right_column,
                    join_type: str = "INNER JOIN"):
    """
    Добавляет JOIN к датасету. Теперь не создает материализованные таблицы,
    а только обновляет метаданные DataSetTable.
    """
    if "JOIN" not in join_type.upper():
        join_type = f"{join_type.strip().upper()} JOIN"

    # Получаем главную таблицу для проверки существования
    main_table = dataset.tables.filter(joined_on_type__isnull=True).first()
    if not main_table:
        raise ValueError("Не найдена главная таблица для датасета")
    
    main_table_name = main_table.table_name
    if not table_exists(main_table_name):
        raise ValueError(f"Таблица {main_table_name} не найдена, JOIN невозможен")
    
    if not table_exists(table.table_name):
        raise ValueError(f"Таблица {table.table_name} не найдена, JOIN невозможен")

    # Проверяем наличие общих значений для валидации JOIN
    with connection.cursor() as c:
        c.execute(f'SELECT DISTINCT "{left_column}" FROM "{main_table_name}" LIMIT 5000')
        main_vals = {r[0] for r in c.fetchall()}
        c.execute(f'SELECT DISTINCT "{right_column}" FROM "{table.table_name}" LIMIT 5000')
        join_vals = {r[0] for r in c.fetchall()}

    if not (main_vals & join_vals):
        raise ValueError("Нет общих значений; авто-JOIN прерван")

    # Обновляем метаданные таблицы для JOIN
    # joined_on_left - колонка в главной (или предыдущей) таблице
    # joined_on_right - колонка в присоединяемой таблице
    table.joined_on_type = join_type
    table.joined_on_left = left_column
    table.joined_on_right = right_column
    table.save(update_fields=['joined_on_type', 'joined_on_left', 'joined_on_right'])

    # Синхронизируем поля датасета после добавления JOIN
    # (можно добавить новые поля из присоединенной таблицы)
    sync_dataset_fields_after_join(dataset, table)

    return left_column

def rebuild_dataset_joins(dataset):
    """
    Перестраивает JOIN'ы для датасета на основе метаданных.
    Теперь не создает материализованные таблицы, только обновляет метаданные.
    """
    base_tbl = dataset.tables.filter(joined_on_type__isnull=True).first()
    if not base_tbl:
        raise ValueError("Не найдена главная таблица")

    # Для файловых источников таблицы не нужны - данные читаются напрямую из файлов
    # Для БД источников проверяем существование таблицы только если это реальная таблица БД
    if base_tbl.file_upload_id is None and base_tbl.table_name:
        # Это БД таблица, проверяем существование
        if not table_exists(base_tbl.table_name):
            raise ValueError(f"Таблица {base_tbl.table_name} не существует")

    # Обновляем table_ref на главную таблицу (для обратной совместимости)
    dataset.table_ref = base_tbl.table_name
    dataset.save(update_fields=["table_ref"])

    # Обновляем метаданные JOIN'ов для всех присоединенных таблиц
    for t in (dataset.tables.filter(joined_on_type__isnull=False).order_by("id")):
        if not t.joined_on_left or not t.joined_on_right:
            continue
            
        # Для файловых источников таблицы не нужны - данные читаются напрямую из файлов
        # Для БД источников проверяем существование таблицы
        if t.file_upload_id is None and t.table_name:
            # Это БД таблица, проверяем существование
            if not table_exists(t.table_name):
                print(f"[WARNING] Таблица {t.table_name} для JOIN не существует, пропускаем")
                continue
        
        # Проверяем валидность JOIN (есть ли общие значения)
        # Только для БД источников (для файловых источников проверка не нужна, данные читаются на лету)
        if base_tbl.file_upload_id is None and t.file_upload_id is None:
            # Обе таблицы - БД источники, проверяем через SQL
            try:
                main_table_name = base_tbl.table_name
                with connection.cursor() as c:
                    c.execute(f'SELECT DISTINCT "{t.joined_on_left}" FROM "{main_table_name}" LIMIT 5000')
                    main_vals = {r[0] for r in c.fetchall()}
                    c.execute(f'SELECT DISTINCT "{t.joined_on_right}" FROM "{t.table_name}" LIMIT 5000')
                    join_vals = {r[0] for r in c.fetchall()}
                
                if not (main_vals & join_vals):
                    print(f"[WARNING] Нет общих значений для JOIN таблицы {t.id}, пропускаем")
                    continue
            except Exception as e:
                print(f"[WARNING] Ошибка проверки JOIN для таблицы {t.id}: {e}")
                continue
        # Для файловых источников проверку пропускаем - валидация будет при выполнении запроса
        
        print(f"Table id={t.id} joined_on_type={t.joined_on_type} joined_on_left={t.joined_on_left} joined_on_right={t.joined_on_right}")
    
    # Синхронизируем поля после всех JOIN'ов
    sync_dataset_fields_after_all_joins(dataset)


def sync_dataset_fields_after_all_joins(dataset):
    """
    Синхронизирует поля датасета после всех JOIN'ов.
    Строит запрос и проверяет доступные колонки.
    """
    try:
        # Используем build_dataset_query для получения списка колонок
        query = build_dataset_query(dataset, limit=0)
        
        # Выполняем запрос для получения структуры
        with connection.cursor() as cursor:
            cursor.execute(query)
            columns = [col[0] for col in cursor.description]
        
        # Получаем существующие поля
        existing_fields = {f.name: f for f in DataSetField.objects.filter(dataset=dataset)}
        
        # Добавляем недостающие поля (используя логику определения source_table)
        for idx, col_name in enumerate(columns):
            if col_name not in existing_fields:
                # Определяем source_table для нового поля
                # Пробуем найти колонку в одной из таблиц датасета
                source_table = None
                for table in dataset.tables.all():
                    try:
                        table_cols = introspect_columns(table.table_name)
                        if col_name in table_cols:
                            source_table = table
                            break
                    except:
                        continue
                
                if source_table:
                    DataSetField.objects.create(
                        dataset=dataset,
                        name=col_name,
                        source_table=source_table,
                        source_column=col_name,
                        order=idx
                    )
    except Exception as e:
        print(f"[SYNC FIELDS AFTER JOINS] Ошибка: {e}")
        # Не прерываем выполнение

def create_temp_table_from_staging(staging_name):
    """
    УСТАРЕВШАЯ ФУНКЦИЯ - больше не создает temp таблицы.
    Оставлена для обратной совместимости.
    """
    print(f"[WARNING] create_temp_table_from_staging вызвана для {staging_name} - функция устарела")
    raise ValidationError("Создание temp таблиц больше не поддерживается. Используйте новую архитектуру с чтением файлов напрямую.")

def get_columns_with_aliases(left_table, right_table):
    left_cols = introspect_columns(left_table)
    right_cols = introspect_columns(right_table)
    left_set = set(left_cols)
    columns = []

    columns += [f'a."{col}" AS "{col}"' for col in left_cols]
    for col in right_cols:
        if col in left_set:
            columns.append(f'b."{col}" AS "{col}__right"')
        else:
            columns.append(f'b."{col}" AS "{col}"')
    return columns

def ensure_temp_table_exists(ds_table):
    """
    УСТАРЕВШАЯ ФУНКЦИЯ - больше не создает таблицы.
    Оставлена для обратной совместимости, но не выполняет никаких действий.
    Для файловых источников таблицы не нужны - данные читаются напрямую из файлов.
    """
    # Функция больше не создает таблицы - они не нужны при новой архитектуре
    # Для файловых источников данные читаются напрямую через pandas
    # Для БД источников таблицы уже существуют в БД
    pass
    
def sync_dataset_fields_with_current_table(dataset):
    table_name = dataset.table_ref
    columns = introspect_columns(table_name)
    existing_fields = {f.source_column: f for f in DataSetField.objects.filter(dataset=dataset)}
    ds_tables = {t.table_name: t for t in DataSetTable.objects.filter(dataset=dataset)}

    # Добавить/обновить поля
    for idx, col in enumerate(columns):
        if col in existing_fields:
            field = existing_fields[col]
            # Можно обновить order, тип данных и т.д., если требуется
            field.order = idx
            field.save(update_fields=['order'])
        else:
            # Определи source_table (по логике как раньше)
            source_tbl = None
            for t in ds_tables.values():
                if col in introspect_columns(t.table_name):
                    source_tbl = t
                    break
            DataSetField.objects.create(
                dataset=dataset,
                name=col,
                source_table=source_tbl,
                source_column=col,
                order=idx
            )

    # Удалить устаревшие поля
    for col, field in existing_fields.items():
        if col not in columns:
            field.delete()


def read_file_to_dataframe(file_upload_id, sheet_name=None):
    """Читает файл в pandas DataFrame.

    Args:
        file_upload_id: идентификатор FileUpload.
        sheet_name: имя листа Excel (опционально).
    """
    upload = FileUpload.objects.get(pk=file_upload_id)
    path = upload.file.path
    sheet = sheet_name or getattr(upload, 'sheet_name', None)
    
    if upload.file_type == 'xlsx':
        read_kwargs = {'header': 0}
        if sheet:
            read_kwargs['sheet_name'] = sheet
        try:
            return pd.read_excel(path, **read_kwargs)
        except ValueError as exc:
            raise ValidationError(f"Лист '{sheet}' не найден в файле") from exc
    elif upload.file_type in ('csv', 'txt'):
        return pd.read_csv(path, encoding='cp1251', on_bad_lines='skip')
    else:
        raise ValidationError(f"Неподдерживаемый тип файла: {upload.file_type}")


def dataframe_to_sql_values(df, table_alias='t0'):
    """
    Преобразует DataFrame в SQL.
    Для небольших файлов использует VALUES, для больших - временную таблицу на время запроса.
    Временная таблица автоматически удалится после выполнения запроса.
    """
    if df.empty:
        return sql.SQL('(SELECT NULL::text AS col WHERE FALSE)'), None
    
    # Для предпросмотра достаточно ограничиться первой 1000 строк
    MAX_VALUES_ROWS = 1000
    if len(df) > MAX_VALUES_ROWS:
        df = df.head(MAX_VALUES_ROWS)
    
    data_rows = []
    for _, row in df.iterrows():
        values = []
        for val in row.values:
            if pd.isna(val):
                values.append('NULL')
            else:
                val_str = str(val).replace("'", "''")
                values.append(f"'{val_str}'")
        data_rows.append(f"({', '.join(values)})")
    
    col_defs = []
    for col in df.columns:
        col_name = str(col).replace('"', '""')
        col_defs.append(f'"{col_name}"')
    
    if len(data_rows) == 0:
        return sql.SQL('(SELECT NULL::text AS col WHERE FALSE)'), None
    
    values_clause = ',\n'.join(data_rows)
    col_list = ', '.join(col_defs)
    
    values_query = f"""
        (VALUES {values_clause}) AS {table_alias}({col_list})
    """
    
    return sql.SQL(values_query), None


def build_dataset_query(dataset, select_fields=None, limit=None, where_clause=None):
    """
    Строит SQL-запрос для датасета на основе метаданных таблиц и полей.
    Для файловых источников читает данные напрямую из файлов без создания таблиц.
    
    Args:
        dataset: объект Dataset
        select_fields: список имен полей для SELECT (None = все поля)
        limit: лимит строк
        where_clause: дополнительное условие WHERE
    
    Returns:
        SQL объект для выполнения запроса
    """
    # Получаем главную таблицу (без JOIN)
    main_table = dataset.tables.filter(joined_on_type__isnull=True).first()
    if not main_table:
        raise ValueError("Не найдена главная таблица для датасета")
    
    # Алиас для главной таблицы
    main_alias = 't0'
    
    # Определяем, является ли источник файловым
    is_file_source = main_table.file_upload_id is not None
    
    if is_file_source:
        # Для файловых источников читаем данные напрямую из файла
        try:
            df = read_file_to_dataframe(
                main_table.file_upload_id,
                sheet_name=getattr(main_table, 'sheet_name', None)
            )
            from_with_alias, _ = dataframe_to_sql_values(df, main_alias)
        except Exception as e:
            raise ValueError(f"Ошибка чтения файла: {str(e)}")
    else:
        # Для БД источников используем прямое подключение к таблице
        table_name = main_table.table_name
        if '.' in table_name:
            schema, table = table_name.split('.', 1)
            from_clause = sql.SQL('{}.{}').format(
                sql.Identifier(schema),
                sql.Identifier(table)
            )
        else:
            from_clause = sql.Identifier(table_name)
        
        from_with_alias = sql.SQL('{} AS {}').format(from_clause, sql.Identifier(main_alias))
    
    # Собираем JOIN'ы
    joins = []
    joined_tables = dataset.tables.filter(joined_on_type__isnull=False).order_by('id')
    
    # Маппинг для отслеживания алиасов таблиц
    table_id_to_alias = {main_table.id: main_alias}
    
    for idx, join_table in enumerate(joined_tables, start=1):
        if not join_table.joined_on_left or not join_table.joined_on_right:
            continue
        
        # Алиас для таблицы в JOIN
        table_alias = f't{idx}'
        table_id_to_alias[join_table.id] = table_alias
        
        # Определяем, является ли присоединяемая таблица файловым источником
        is_join_file_source = join_table.file_upload_id is not None
        
        if is_join_file_source:
            # Для файловых источников читаем данные напрямую из файла
            try:
                df_join = read_file_to_dataframe(
                    join_table.file_upload_id,
                    sheet_name=getattr(join_table, 'sheet_name', None)
                )
                join_table_ref, _ = dataframe_to_sql_values(df_join, table_alias)
            except Exception as e:
                raise ValueError(f"Ошибка чтения файла для JOIN: {str(e)}")
        else:
            # Для БД источников используем прямое подключение к таблице
            join_table_name = join_table.table_name
            if '.' in join_table_name:
                join_schema, join_table_only = join_table_name.split('.', 1)
                join_table_ref = sql.SQL('{}.{}').format(
                    sql.Identifier(join_schema),
                    sql.Identifier(join_table_only)
                )
            else:
                join_table_ref = sql.Identifier(join_table_name)
            
            join_table_ref = sql.SQL('{} AS {}').format(join_table_ref, sql.Identifier(table_alias))
        
        # Тип JOIN
        join_type = (join_table.joined_on_type or 'LEFT JOIN').strip().upper()
        if 'JOIN' not in join_type:
            join_type = f'{join_type} JOIN'
        
        # Определяем левую таблицу для JOIN
        # joined_on_left - это колонка в главной таблице (или предыдущей joined таблице)
        # Для простоты будем считать, что left_column всегда из главной таблицы
        left_table_alias = main_alias  # По умолчанию главная таблица
        
        # Условие JOIN: left_column из левой таблицы = right_column из join таблицы
        join_condition = sql.SQL('{}.{} = {}.{}').format(
            sql.Identifier(left_table_alias),
            sql.Identifier(join_table.joined_on_left),
            sql.Identifier(table_alias),
            sql.Identifier(join_table.joined_on_right)
        )
        
        if is_join_file_source:
            # Для файловых источников VALUES уже содержит алиас, поэтому просто добавляем JOIN
            join_clause = sql.SQL('{} {} ON {}').format(
                sql.SQL(join_type),
                join_table_ref,
                join_condition
            )
        else:
            join_clause = sql.SQL('{} {} ON {}').format(
                sql.SQL(join_type),
                join_table_ref,
                join_condition
            )
        joins.append(join_clause)
    
    # Строим SELECT часть
    if select_fields is None:
        # Берем все поля датасета
        fields = dataset.fields.all().order_by('order')
    else:
        # Берем только указанные поля
        fields = dataset.fields.filter(name__in=select_fields).order_by('order')
    
    select_parts = []
    table_aliases = {}
    
    # Маппинг таблиц к алиасам (используем уже построенный table_id_to_alias)
    table_aliases = table_id_to_alias.copy()
    
    for field in fields:
        # Определяем выражение для поля
        if field.expression:
            # Используем выражение напрямую (должно содержать валидный SQL)
            # Осторожно: expression может содержать сложный SQL, поэтому используем SQL()
            # Будем предполагать, что expression уже содержит правильный SQL с алиасами
            field_expr = sql.SQL(field.expression)
        else:
            # Используем source_column из source_table
            table_alias = table_aliases.get(field.source_table.id, main_alias)
            field_expr = sql.SQL('{}.{}').format(
                sql.Identifier(table_alias),
                sql.Identifier(field.source_column)
            )
        
        select_parts.append(
            sql.SQL('{} AS {}').format(
                field_expr,
                sql.Identifier(field.name)
            )
        )
    
    if not select_parts:
        # Если нет полей, выбираем все колонки из главной таблицы
        select_parts.append(sql.SQL('{}.*').format(sql.Identifier(main_alias)))
    
    # Собираем итоговый запрос
    query_parts = [
        sql.SQL('SELECT {}').format(sql.SQL(', ').join(select_parts)),
        sql.SQL('FROM {}').format(from_with_alias)
    ]
    
    # Добавляем JOIN'ы
    query_parts.extend(joins)
    
    # Добавляем WHERE если есть
    if where_clause:
        query_parts.append(sql.SQL('WHERE {}').format(sql.SQL(where_clause)))
    
    # Добавляем LIMIT если есть
    if limit is not None:
        query_parts.append(sql.SQL('LIMIT {}').format(sql.Literal(limit)))
    
    final_query = sql.SQL(' ').join(query_parts)
    return final_query


def get_dataset_table_alias(dataset, table_id):
    """Возвращает алиас таблицы в запросе датасета."""
    main_table = dataset.tables.filter(joined_on_type__isnull=True).first()
    if main_table and main_table.id == table_id:
        return 't0'
    
    joined_tables = dataset.tables.filter(joined_on_type__isnull=False).order_by('id')
    for idx, join_table in enumerate(joined_tables, start=1):
        if join_table.id == table_id:
            return f't{idx}'
    
    return 't0'  # По умолчанию


