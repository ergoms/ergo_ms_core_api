from uuid import uuid4
from django.core.files import File
from django.db import transaction, connection, ProgrammingError
from django.shortcuts import get_object_or_404
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from .models import Connection

from rest_framework import (
    generics,
    permissions,
    status,
    viewsets
)
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.response import Response
from rest_framework.views import APIView

from openpyxl import load_workbook
import tempfile, os, openpyxl, csv

from src.core.bi_analysis.bi_datasets.models import Dataset, FileUpload, DataSetTable, DataSetField, DatasetParam
from src.core.bi_analysis.bi_datasets.serializers import (
    DatasetDetailSerializer,
    DatasetSerializer,
    FileUploadSerializer,
    DataSetTableSerializer,
    DataSetFieldSerializer,
    DatasetShortSerializer, 
    DatasetUpdateSerializer,
    DatasetDetailFullSerializer,
    DatasetParamSerializer
)

from src.core.bi_analysis.services.services import (
    create_temp_table_from_source,
    import_file_upload_to_table,
    populate_initial_fields,
    populate_initial_fields_from_file,
    auto_join_table,
    introspect_columns,
    rebuild_dataset_joins,
    table_exists
)

from ..bi_charts.methods import get_rows_for_chart

# ==============================================================================
# Dataset endpoints
# ==============================================================================

class DatasetRowsAPIView(APIView):
    def get(self, request, pk):
        dataset = get_object_or_404(Dataset, pk=pk, owner=request.user)
        chart_fields = dataset.fields.all()
        rows = get_rows_for_chart(dataset, chart_fields)
        return Response(rows)

class DatasetListCreateView(generics.ListCreateAPIView):
    queryset = Dataset.objects.all()
    serializer_class = DatasetSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Для генерации схемы Swagger возвращаем пустой queryset
            return Dataset.objects.none()
        return (Dataset.objects
            .filter(owner=self.request.user)
            .only('id', 'name', 'created_at', 'owner')
            .order_by('-created_at'))

    def get_serializer_class(self):
        # Для списка отдаём короткий сериализатор, чтобы не тянуть связанные таблицы/поля
        if self.request and self.request.method == 'GET':
            return DatasetShortSerializer
        return DatasetSerializer

    @transaction.atomic
    def perform_create(self, serializer):
        dataset = serializer.save(owner=self.request.user)
        if not dataset.file_source:
            raise ValidationError("file_source is required for dataset creation")

        # НЕ создаем таблицы в БД - используем метаданные и читаем файлы напрямую
        # table_ref оставляем пустым или используем имя файла для обратной совместимости
        dataset.table_ref = None  # Больше не нужна материализованная таблица
        dataset.save(update_fields=['table_ref'])

        # Создаем DataSetTable с ссылкой на file_upload
        # table_name может быть пустым или содержать имя для отображения
        main_table = DataSetTable.objects.create(
            dataset=dataset,
            connection=dataset.connection,
            table_name=dataset.file_source.original_filename or f"file_{dataset.file_source.id}",  # Имя для отображения
            joined_on={},
            file_upload=dataset.file_source 
        )
        
        if dataset.file_source and dataset.file_source.columns_info:
            main_table.columns_info = dataset.file_source.columns_info
            main_table.save(update_fields=["display_name", "columns_info"])

        # Создаем поля на основе информации о колонках из файла
        populate_initial_fields_from_file(dataset, dataset.file_source, main_table)
        
        fields_data = self.request.data.get('fields', [])
        if fields_data:
            for field in fields_data:
                obj = dataset.fields.filter(name=field.get('name')).first()
                if obj:
                    update_fields = []
                    if 'aggregation' in field:
                        obj.aggregation = field['aggregation']
                        update_fields.append('aggregation')
                    if 'type' in field:
                        obj.type = field['type']
                        update_fields.append('type')
                    if update_fields:
                        obj.save(update_fields=update_fields)
        params_data = self.request.data.get('params')
        if params_data is not None:
            # поддержка формата из фронта: [{name,type,defaultValue,sourceUsage,...}]
            try:
                items = []
                for i, p in enumerate(params_data or []):
                    if not isinstance(p, dict):
                        continue
                    items.append({
                        'name': p.get('name'),
                        'type': p.get('type') or 'string',
                        'default_value': p.get('defaultValue', p.get('default')),
                        'source_usage': p.get('sourceUsage', False),
                        'order': p.get('order', i),
                        'description': p.get('description', ''),
                    })
                dataset.set_params_items(items)
            except Exception as e:
                # не прерываем создание датасета из-за параметров
                print(f"[DatasetListCreateView] params save failed: {e}")
        
class DatasetRemoveRelationView(APIView):
    """
    POST /bi_analysis/bi_datasets/<pk>/remove-relation/
    { "right_table_id": 1339 }
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        right_id = request.data.get("right_table_id")
        if not right_id:
            return Response(
                {"success": False, "error": "right_table_id is required"}, status=400
            )

        dataset = get_object_or_404(Dataset, pk=pk, owner=request.user)
        try:
            tbl = dataset.tables.get(pk=right_id)
        except DataSetTable.DoesNotExist:
            return Response(
                {"success": False, "error": "table not found in dataset"}, status=404
            )

        # Удаляем все поля из DataSetField, которые ссылаются на эту таблицу
        deleted_fields, _ = dataset.fields.filter(source_table=tbl).delete()

        # Очищаем связь
        tbl.joined_on_type = tbl.joined_on_left = tbl.joined_on_right = None
        tbl.joined_on = {}
        tbl.save()

        from ..services.services import rebuild_dataset_joins
        rebuild_dataset_joins(dataset)

        serializer = DatasetDetailSerializer(dataset)
        return Response({"success": True, "dataset": serializer.data})


class DatasetListView(generics.ListAPIView):
    serializer_class = DatasetShortSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Для генерации схемы Swagger возвращаем пустой queryset
            return Dataset.objects.none()
        return (Dataset.objects
            .filter(owner=self.request.user)
            .order_by('-created_at'))

class DatasetDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Dataset.objects.all()
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Для генерации схемы Swagger возвращаем пустой queryset
            return Dataset.objects.none()
        return Dataset.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        if self.request.method in ('PUT', 'PATCH'):
            return DatasetUpdateSerializer
        return DatasetDetailFullSerializer
    
class DataSetTableColumnsView(APIView):
    def get(self, request, pk):
        # pk — это id DataSetTable
        try:
            tbl = DataSetTable.objects.get(pk=pk)
        except DataSetTable.DoesNotExist:
            return Response({'error': 'Table not found'}, status=404)
        # Получаем все DataSetField, относящиеся к этой таблице
        fields = DataSetField.objects.filter(source_table=tbl)
        columns = [f.source_column or f.name for f in fields]
        return Response({'columns': columns})
    

class DatasetJoinTableView(APIView):
    """
    Прицепить (или переприцепить) staging-таблицу к датасету.
    POST body:
        {
            "staging_name": "temp_abcd1234…",
            "left_column" : "Город",
            "right_column": "Город",
            "join_type"   : "INNER JOIN"   # опционально, default — INNER JOIN
        }
    """
    permission_classes = []

    def post(self, request, pk, *args, **kwargs):
        dataset = get_object_or_404(Dataset, pk=pk)

        staging_name = request.data.get("staging_name") or request.data.get("stagingName")
        left_column  = request.data.get("left_column")  or request.data.get("leftColumn")
        right_column = request.data.get("right_column") or request.data.get("rightColumn")
        join_type    = (request.data.get("join_type")   or
                        request.data.get("joinType")    or
                        "INNER JOIN").upper()

        if not all([staging_name, left_column, right_column]):
            return Response(
                {"success": False, "error": "staging_name, left_column и right_column обязательны"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            auto_join_table(
                dataset        = dataset,
                staging_name   = staging_name,
                left_column    = left_column,
                right_column   = right_column,
                join_type      = join_type,
            )
        except Exception as exc:
            return Response(
                {"success": False, "error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"success": True})

class DatasetAddRelationView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, dataset_id):
        from src.core.bi_analysis.bi_datasets.models import DataSetTable, FileUpload

        dataset = Dataset.objects.get(id=dataset_id)
        right_table_id = int(request.data.get('rightTableId'))
        join_type = request.data.get('joinType')
        lines = request.data.get('lines', [])
        if not lines:
            return Response({'error': 'Нет пар колонок для соединения'}, status=400)
        left_col = lines[0]['left']
        right_col = lines[0]['right']

        file_upload = None

        file_id = request.data.get("file_id")
        if file_id:
            try:
                file_upload = FileUpload.objects.get(pk=file_id)
            except FileUpload.DoesNotExist:
                return Response({'error': f'Файл с id={file_id} не найден.'}, status=404)
        else:
            try:
                ds_table = DataSetTable.objects.get(pk=right_table_id)
                file_upload = ds_table.file_upload
            except DataSetTable.DoesNotExist:
                try:
                    file_upload = FileUpload.objects.get(pk=abs(right_table_id))
                except FileUpload.DoesNotExist:
                    return Response({'error': f'Не найден ни DataSetTable, ни FileUpload с id={right_table_id}'}, status=404)
        existing = dataset.tables.filter(pk=right_table_id).first()
        if existing:
            existing.joined_on_type  = join_type.upper()
            existing.joined_on_left  = left_col
            existing.joined_on_right = right_col
            existing.save(update_fields=["joined_on_type", "joined_on_left", "joined_on_right"])
            return Response({"success": True})

        if not file_upload:
            return Response({'error': f'Файл для связи с id={right_table_id} не найден.'}, status=404)

        tbl = DataSetTable.objects.create(
            dataset=dataset,
            connection=dataset.connection,
            file_upload=file_upload,
            display_name=file_upload.original_filename,
            columns_info=file_upload.columns_info,
            table_name=f"temp_{uuid4().hex}",
            joined_on_type=join_type.upper(),
            joined_on_left=left_col,
            joined_on_right=right_col,
        )
        
        rebuild_dataset_joins(dataset)
        return Response({'success': True})
        
class AddTableToDatasetView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        file_id = request.data.get('file_id')
        dataset = Dataset.objects.get(pk=pk)

        file_upload = FileUpload.objects.get(pk=file_id)
        connection = file_upload.connection or dataset.connection

        # НЕ создаем таблицы в БД - используем только метаданные
        # table_name используется только для отображения/идентификации
        table_display_name = file_upload.original_filename or f"file_{file_upload.id}"

        data_table = DataSetTable.objects.create(
            dataset=dataset,
            connection=connection,
            table_name=table_display_name,  # Имя для отображения, не реальная таблица
            joined_on={},
            file_upload=file_upload
        )

        return Response({
            "id": data_table.id,
            "table_ref": None,  # Больше не используется
            "name": data_table.table_name,
            "display_name": file_upload.original_filename,
        })

# ==============================================================================
# DatasetViewSet (альтернатива generic views)
# ==============================================================================
    
class DatasetPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        dataset = Dataset.objects.filter(pk=pk, owner=request.user).first()
        if not dataset:
            return Response({"detail": "Not found"}, status=404)

        limit = int(request.query_params.get('limit', 1000))
        offset = int(request.query_params.get('offset', 0))
        search = request.query_params.get('search', '').strip()
        use_async = request.query_params.get('async', 'false').lower() == 'true'
        
        # Для больших лимитов используем асинхронную обработку
        if use_async or limit > 100:
            from src.core.bi_analysis.tasks import process_dataset_preview
            task = process_dataset_preview.delay(pk, limit)
            return Response({
                "task_id": task.id,
                "status": "processing",
                "message": "Предпросмотр обрабатывается асинхронно"
            }, status=202)
        
        try:
            from src.core.bi_analysis.services.services import build_dataset_query
            
            # Проверяем, есть ли таблицы в датасете
            if not dataset.tables.exists():
                # Fallback для старых датасетов с table_ref
                if not dataset.table_ref:
                    return Response({"detail": "Таблица ещё не создана для датасета"}, status=400)
                
                base_table = dataset.table_ref
                if '.' in base_table:
                    schema, table = base_table.split('.', 1)
                else:
                    schema, table = 'public', base_table
                
                # Строим запрос с поиском и пагинацией
                query_parts = [f'SELECT * FROM "{schema}"."{table}"']
                
                if search:
                    # Получаем колонки для поиска
                    with connection.cursor() as cursor:
                        cursor.execute(f'SELECT * FROM "{schema}"."{table}" LIMIT 0')
                        columns = [col[0] for col in cursor.description]
                    
                    search_conditions = [f'CAST("{col}" AS TEXT) ILIKE %s' for col in columns]
                    query_parts.append(f"WHERE ({' OR '.join(search_conditions)})")
                    params = [f'%{search}%'] * len(columns)
                else:
                    params = []
                
                query_parts.append(f'LIMIT %s OFFSET %s')
                params.extend([limit, offset])
                
                with connection.cursor() as cursor:
                    cursor.execute(' '.join(query_parts), params)
                    rows = cursor.fetchall()
                    columns = [col[0] for col in cursor.description]
            else:
                # Используем новую логику с динамическим SQL
                query = build_dataset_query(
                    dataset, 
                    limit=limit, 
                    offset=offset,
                    search=search if search else None
                )
                
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    columns = [col[0] for col in cursor.description]
                    
        except ValueError as e:
            return Response({"detail": str(e)}, status=400)
        except ProgrammingError as e:
            return Response({"detail": f"Ошибка выполнения запроса: {str(e)}"}, status=500)
        except Exception as e:
            return Response({"detail": f"Ошибка: {str(e)}"}, status=500)

        return Response({
            "columns": columns,
            "rows": rows,
            "has_more": len(rows) == limit  # Указываем, есть ли еще данные
        })


class DatasetPreviewTaskStatusView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """
        Получает статус и результат асинхронной задачи предпросмотра.
        """
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({"detail": "Не указан task_id"}, status=400)
        
        try:
            from celery.result import AsyncResult
            from src.config.celery import celery_app
            
            task = AsyncResult(task_id, app=celery_app)
            
            if task.state == 'PENDING':
                response = {
                    'task_id': task_id,
                    'status': 'pending',
                    'message': 'Задача ожидает выполнения'
                }
            elif task.state == 'PROGRESS':
                response = {
                    'task_id': task_id,
                    'status': 'processing',
                    'message': 'Задача выполняется',
                    'progress': task.info.get('progress', 0) if isinstance(task.info, dict) else None
                }
            elif task.state == 'SUCCESS':
                result = task.result
                response = {
                    'task_id': task_id,
                    'status': 'success',
                    'result': result
                }
            elif task.state == 'FAILURE':
                response = {
                    'task_id': task_id,
                    'status': 'failure',
                    'error': str(task.info) if task.info else 'Неизвестная ошибка'
                }
            else:
                response = {
                    'task_id': task_id,
                    'status': task.state.lower(),
                    'message': f'Статус задачи: {task.state}'
                }
            
            return Response(response, status=200)
            
        except Exception as e:
            return Response({"detail": f"Ошибка получения статуса задачи: {str(e)}"}, status=500)


class DatasetColumnsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        dataset = Dataset.objects.filter(pk=pk, owner=request.user).first()
        if not dataset:
            return Response({"detail": "Dataset not found"}, status=404)

        # Получаем поля датасета с их типами
        fields = dataset.fields.all()
        cols = []
        for f in fields:
            cols.append({
                "id": f.id,
                "name": f.name,
                "type": f.type,
                "aggregation": f.aggregation,
            })

        return Response({"columns": cols})

class DatasetDraftPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Принимает черновик датасета (главная таблица + join'ы), возвращает предпросмотр данных.
        Работает без создания постоянных таблиц - читает файлы напрямую через polars.
        Поддерживает асинхронную обработку через celery для больших файлов.
        """
        from src.core.bi_analysis.services.services import read_file_to_dataframe, dataframe_to_sql_values
        from psycopg2 import sql
        
        data = request.data
        use_async = data.get('async', False)
        limit = int(data.get('limit', 20))
        
        # Для больших лимитов или множества файлов используем асинхронную обработку
        file_count = sum([
            1 if 'file_id' in data.get('mainTable', {}) and data.get('mainTable', {}).get('file_id') else 0,
            sum([1 if 'file_id' in jt and jt.get('file_id') else 0 for jt in data.get('joinedTables', [])])
        ])
        
        if use_async or limit > 100 or file_count > 2:
            from src.core.bi_analysis.tasks import process_draft_preview
            task = process_draft_preview.delay(data)
            return Response({
                "task_id": task.id,
                "status": "processing",
                "message": "Предпросмотр обрабатывается асинхронно"
            }, status=202)
        
        connection_id = data.get('connection_id')
        main_table = data.get('mainTable')
        joined_tables = data.get('joinedTables', [])
        limit = int(data.get('limit', 20))

        def get_sheet_name(table_dict):
            if not isinstance(table_dict, dict):
                return None
            sheet = (
                table_dict.get('sheet_name') or
                table_dict.get('sheetName') or
                table_dict.get('sheet')
            )
            if sheet:
                return sheet
            nested_file = table_dict.get('file_upload') or {}
            if isinstance(nested_file, dict):
                return nested_file.get('sheet_name') or nested_file.get('sheet')
            return None

        # Определяем, является ли главная таблица файловым источником
        is_main_file = 'file_id' in main_table and main_table.get('file_id')
        
        # Формируем FROM для главной таблицы
        main_alias = 'a'
        
        if is_main_file:
            # Для файловых источников читаем данные напрямую
            try:
                df_main = read_file_to_dataframe(
                    main_table['file_id'],
                    sheet_name=get_sheet_name(main_table)
                )
                main_from, _ = dataframe_to_sql_values(df_main, main_alias)
                main_cols = [str(col) for col in df_main.columns]
            except Exception as e:
                raise ValidationError(f"Ошибка чтения главного файла: {str(e)}")
        else:
            # Для БД источников используем прямое подключение
            table_name = main_table.get('table_name')
            if not table_name:
                raise ValidationError("Не указано имя таблицы для БД источника")
            
            if '.' in table_name:
                schema, table = table_name.split('.', 1)
                main_from = sql.SQL('{}.{} AS {}').format(
                    sql.Identifier(schema),
                    sql.Identifier(table),
                    sql.Identifier(main_alias)
                )
            else:
                main_from = sql.SQL('{} AS {}').format(
                    sql.Identifier(table_name),
                    sql.Identifier(main_alias)
                )
            
            # Получаем колонки из БД таблицы
            main_cols = introspect_columns(table_name)
        
        # Формируем SELECT - берем все колонки главной таблицы
        select_parts = [sql.SQL('{}.{} AS {}').format(
            sql.Identifier(main_alias),
            sql.Identifier(col),
            sql.Identifier(col)
        ) for col in main_cols]
        
        # Обрабатываем JOIN'ы
        join_clauses = []
        alias_idx = ord('b')
        all_cols = set(main_cols)
        
        for jt in joined_tables:
            tbl_alias = chr(alias_idx)
            alias_idx += 1
            
            # Определяем, является ли JOIN таблица файловым источником
            is_join_file = 'file_id' in jt and jt.get('file_id')
            
            if is_join_file:
                # Для файловых источников читаем данные напрямую
                try:
                    df_join = read_file_to_dataframe(
                        jt['file_id'],
                        sheet_name=get_sheet_name(jt)
                    )
                    join_from, _ = dataframe_to_sql_values(df_join, tbl_alias)
                    join_cols = [str(col) for col in df_join.columns]
                except Exception as e:
                    raise ValidationError(f"Ошибка чтения файла для JOIN: {str(e)}")
            else:
                # Для БД источников используем прямое подключение
                table_name = jt.get('table_name')
                if not table_name:
                    raise ValidationError("Не указано имя таблицы для JOIN БД источника")
                
                if '.' in table_name:
                    schema, table = table_name.split('.', 1)
                    join_from = sql.SQL('{}.{} AS {}').format(
                        sql.Identifier(schema),
                        sql.Identifier(table),
                        sql.Identifier(tbl_alias)
                    )
                else:
                    join_from = sql.SQL('{} AS {}').format(
                        sql.Identifier(table_name),
                        sql.Identifier(tbl_alias)
                    )
                
                join_cols = introspect_columns(table_name)
            
            # Добавляем колонки из JOIN таблицы (только уникальные)
            for col in join_cols:
                if col not in all_cols:
                    select_parts.append(sql.SQL('{}.{} AS {}').format(
                        sql.Identifier(tbl_alias),
                        sql.Identifier(col),
                        sql.Identifier(col)
                    ))
                    all_cols.add(col)
            
            # Формируем условие JOIN
            join_type = jt.get('joinType', 'LEFT JOIN').strip().upper()
            if 'JOIN' not in join_type:
                join_type = f'{join_type} JOIN'
            
            lines = jt.get('lines') or []
            if not lines or not lines[0].get('left') or not lines[0].get('right'):
                raise ValidationError("Не указаны поля для join'а")
            
            left_col = lines[0]['left']
            right_col = lines[0]['right']
            
            join_condition = sql.SQL('{}.{} = {}.{}').format(
                sql.Identifier(main_alias),
                sql.Identifier(left_col),
                sql.Identifier(tbl_alias),
                sql.Identifier(right_col)
            )
            
            join_clause = sql.SQL('{} {} ON {}').format(
                sql.SQL(join_type),
                join_from,
                join_condition
            )
            join_clauses.append(join_clause)
        
        # Собираем итоговый запрос
        query_parts = [
            sql.SQL('SELECT {}').format(sql.SQL(', ').join(select_parts)),
            sql.SQL('FROM {}').format(main_from)
        ]
        
        query_parts.extend(join_clauses)
        query_parts.append(sql.SQL('LIMIT {}').format(sql.Literal(limit)))
        
        final_query = sql.SQL(' ').join(query_parts)
        
        # Выполняем запрос
        with connection.cursor() as cursor:
            cursor.execute(final_query)
            rows = cursor.fetchall()
            columns = [col[0] for col in cursor.description]

        return Response({
            "columns": columns,
            "rows": rows
        })

# ==============================================================================
# DataSetTable endpoints
# ==============================================================================

class DataSetTableViewSet(viewsets.ModelViewSet):
    queryset = DataSetTable.objects.all()
    serializer_class = DataSetTableSerializer
    permission_classes = [permissions.IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save()
    
class RenameDatasetColumnsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        dataset = Dataset.objects.get(pk=pk, owner=request.user)
        renames = request.data.get('renames', [])
        table_ref = dataset.table_ref
        schema, table = ('public', table_ref)
        if '.' in table_ref:
            schema, table = table_ref.split('.', 1)

        with connection.cursor() as cursor:
            for rename in renames:
                cursor.execute(
                    f'ALTER TABLE "{schema}"."{table}" RENAME COLUMN "{rename["old_name"]}" TO "{rename["new_name"]}";'
                )
                DataSetField.objects.filter(
                    dataset=dataset, source_column=rename["old_name"]
                ).update(name=rename["new_name"], source_column=rename["new_name"])
        return Response({"status": "ok"})

# ==============================================================================
# DataSetField endpoints
# ==============================================================================

class DataSetFieldViewSet(viewsets.ModelViewSet):
    serializer_class = DataSetFieldSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        dataset_id = self.request.query_params.get('dataset')
        queryset = DataSetField.objects.all()
        if dataset_id:
            queryset = queryset.filter(dataset_id=dataset_id)
        return queryset

# ==============================================================================
# DatasetParam endpoints
# ==============================================================================

from src.core.utils.mixins import SwaggerSafeMixin

class DatasetParamViewSet(SwaggerSafeMixin, viewsets.ModelViewSet):
    serializer_class = DatasetParamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        base = DatasetParam.objects.select_related('dataset')
        user = self.get_safe_user()
        if user is None:
            return base.none()
        qs = base.filter(dataset__owner=user)
        dataset_id = self.request.query_params.get('dataset')
        if dataset_id:
            qs = qs.filter(dataset_id=dataset_id)
        return qs.order_by('order', 'id')

# ==============================================================================
# FileUpload endpoints
# ==============================================================================

class TempUploadView(APIView):
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'Файл не передан'}, status=400)
        suffix = os.path.splitext(file.name)[-1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            for chunk in file.chunks():
                tmp.write(chunk)
            temp_path = tmp.name
        return Response({
            'temp_path': temp_path,
            'original_filename': file.name,
            'file_type': suffix.lstrip('.').lower()
        }, status=201)

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Для генерации схемы Swagger возвращаем пустой queryset
            return FileUpload.objects.none()
        return FileUpload.objects.filter(owner=self.request.user)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)

class FileUploadDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    GET    /upload/{pk}/    — метаданные + предпросмотр содержимого
    PUT    /upload/{pk}/    — изменить имя/загрузить новый файл
    DELETE /upload/{pk}/    — удалить запись и файл на диске
    """
    serializer_class = FileUploadSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            # Для генерации схемы Swagger возвращаем пустой queryset
            return FileUpload.objects.none()
        return FileUpload.objects.filter(owner=self.request.user)
    
    def perform_create(self, serializer):
        instance = serializer.save(owner=self.request.user)
        columns_info = self._extract_columns_info(instance)
        instance.columns_info = columns_info
        instance.save(update_fields=['columns_info'])

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        data = serializer.data

        if not instance.file or not hasattr(instance.file, 'path'):
            data['parsed'] = []
            return Response(data)

        encoding   = request.query_params.get('encoding', 'utf-8')
        delimiter  = request.query_params.get('delimiter', ',')
        has_header = request.query_params.get('has_header', 'true').lower() == 'true'

        try:
            if instance.file_type in ('csv', 'txt'):
                parsed = self._parse_csv(instance.file.path, encoding, delimiter, has_header)

            elif instance.file_type == 'xlsx':
                parsed, sheets = self._parse_xlsx(instance.file.path, has_header)
                data['sheets'] = sheets

            else:
                raise ValidationError(f"Неподдерживаемый тип файла: {instance.file_type}")

            data['parsed'] = parsed
            return Response(data)

        except Exception as exc:
            return Response({'error': str(exc)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def perform_update(self, serializer):
        file = self.request.FILES.get('file')
        name = self.request.data.get('name')
        sheet = self.request.data.get('sheet')  # Добавляем поддержку листа
        file_type = (file.name.split('.')[-1].lower()
                     if file else 
                     (name.split('.')[-1].lower() if name and '.' in name else None))

        # Если есть новый файл и указан лист - обрабатываем листы
        if file and file_type == 'xlsx' and sheet:
            print(f"[DEBUG UPDATE] Обновляем Excel файл с листом: {sheet}")
            suffix = os.path.splitext(file.name)[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                for chunk in file.chunks():
                    tmp.write(chunk)
                temp_path = tmp.name
            
            try:
                wb = load_workbook(temp_path, read_only=False)
                print(f"[DEBUG UPDATE] Доступные листы: {wb.sheetnames}")
                
                # Удаляем все листы кроме нужного
                sheets_to_remove = [ws_name for ws_name in wb.sheetnames if ws_name != sheet]
                for ws_name in sheets_to_remove:
                    ws = wb[ws_name]
                    wb.remove(ws)
                
                single_sheet_path = temp_path + "_single.xlsx"
                wb.save(single_sheet_path)
                wb.close()
                print(f"[DEBUG UPDATE] Обновляем файл одним листом: {single_sheet_path}")
                
                # Сначала сохраняем экземпляр без файла
                instance = serializer.save(
                    name=name or serializer.instance.name,
                    original_filename=file.name,
                    file_type=file_type
                )
                
                # Удаляем старый файл если он есть
                if instance.file and hasattr(instance.file, 'path') and os.path.exists(instance.file.path):
                    try:
                        old_path = instance.file.path
                        instance.file.delete(save=False)
                        print(f"[DEBUG UPDATE] Удален старый файл: {old_path}")
                    except Exception as e:
                        print(f"[DEBUG UPDATE] Ошибка при удалении старого файла: {e}")
                
                # Затем обновляем файл отдельно
                with open(single_sheet_path, 'rb') as f:
                    instance.file.save(file.name, File(f), save=True)
                
                print(f"[DEBUG UPDATE] Файл обновлен в базе: {instance.file.path}")
                
                # Очищаем временные файлы
                try:
                    os.remove(single_sheet_path)
                    os.remove(temp_path)
                except Exception as e:
                    print(f"[DEBUG UPDATE] Ошибка при удалении временных файлов: {e}")
                    
            except Exception as e:
                print(f"[DEBUG UPDATE] Ошибка при обработке листов: {e}")
                # Если не удалось обработать листы, сохраняем как есть
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
                instance = serializer.save(
                    name=name or serializer.instance.name,
                    original_filename=(file.name if file else serializer.instance.original_filename),
                    file=(file if file else serializer.instance.file),
                    file_type=file_type
                )
        else:
            instance = serializer.save(
                name=name or serializer.instance.name,
                original_filename=(file.name if file else serializer.instance.original_filename),
                file=(file if file else serializer.instance.file),
                file_type=file_type
            )

        columns_info = self._extract_columns_info(instance)
        instance.columns_info = columns_info
        instance.save(update_fields=['columns_info'])

    @staticmethod
    def _extract_columns_info(instance):
        path = instance.file.path
        if instance.file_type == 'xlsx':
            try:
                wb = load_workbook(filename=path, read_only=True)
                sheet = wb.active
                columns = [cell.value for cell in next(sheet.rows)]
                return {'columns': columns}
            except Exception:
                return {'columns': []}
        elif instance.file_type == 'csv':
            try:
                with open(path, encoding='utf-8') as f:
                    reader = csv.reader(f)
                    columns = next(reader, [])
                return {'columns': columns}
            except Exception:
                return {'columns': []}
        return {'columns': []}

    def perform_destroy(self, instance):
        # удаляем сам файл
        if instance.file and os.path.isfile(instance.file.path):
            try:
                os.remove(instance.file.path)
            except PermissionError:
                import gc
                gc.collect()
                raise ValidationError("Файл занят другим процессом.")
        instance.delete()

    # -----------------------------
    # вспомогательные методы
    # -----------------------------
    @staticmethod
    def _parse_csv(path, encoding, delimiter, has_header):
        with open(path, 'r', encoding=encoding) as f:
            reader = csv.reader(f, delimiter='\t' if delimiter == '\\t' else delimiter)
            rows = list(reader)
        if not has_header and rows:
            alph = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            headers = [alph[i] if i < len(alph) else f"Col{i}" for i in range(len(rows[0]))]
            rows.insert(0, headers)
        return rows

    @staticmethod
    def _parse_xlsx(path, has_header):
        wb = load_workbook(filename=path, read_only=True)
        sheet = wb.sheetnames[0]
        ws = wb[sheet]
        data = list(ws.values)
        if not has_header:
            return data, wb.sheetnames
        headers, *body = data
        return [list(headers), *body], wb.sheetnames

class FileUploadByConnectionView(generics.ListAPIView):
    """
    GET /connection/{id}/files/ — файлы, загруженные к указанному соединению
    """
    serializer_class = FileUploadSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        conn_id = self.kwargs['connection_id']
        return FileUpload.objects.filter(owner=self.request.user, connection_id=conn_id).order_by('-uploaded_at')
    
class DatasetRowsAggAPIView(APIView):
    """
    POST  .../datasets/<dataset_id>/rows-agg/
    body = { "fields": {... exactly Chart.params ...} }
    """
    def post(self, request, pk):
        ds = get_object_or_404(Dataset, pk=pk)
        chart_fields = []
        for group_key, field_list in (request.data.get('fields') or {}).items():
            chart_fields.extend(field_list)
        data = get_rows_for_chart(ds, chart_fields)
        return Response(data)

def detect_column_type(values):
    filtered = [v for v in values if v not in (None, '')]
    if not filtered:
        return "string"
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in filtered):
        if all(isinstance(v, int) for v in filtered):
            return "integer"
        return "float"
    try:
        import dateutil.parser
        if all(isinstance(dateutil.parser.parse(str(v)), object) for v in filtered):
            return "date"
    except Exception:
        pass
    # bool
    if all(str(v).lower() in ('true', 'false') for v in filtered):
        return "bool"
    return "string"

def extract_columns_info(instance):
    path = instance.file.path
    if instance.file_type == 'xlsx':
        try:
            wb = openpyxl.load_workbook(filename=path, read_only=True)
            sheet = wb.active
            rows = list(sheet.iter_rows(values_only=True))
            headers = rows[0] if rows else []
            columns = list(headers)
            types = []
            for col_idx in range(len(columns)):
                col_values = [row[col_idx] for row in rows[1:50] if len(row) > col_idx]  # до 50 строк
                types.append(detect_column_type(col_values))
            return {'columns': columns, 'types': types}
        except Exception:
            return {'columns': [], 'types': []}

    elif instance.file_type == 'csv':
        try:
            with open(path, encoding='utf-8') as f:
                reader = csv.reader(f)
                rows = list(reader)
                headers = rows[0] if rows else []
            columns = list(headers)
            types = []
            for col_idx in range(len(columns)):
                col_values = [row[col_idx] for row in rows[1:50] if len(row) > col_idx]
                types.append(detect_column_type(col_values))
            return {'columns': columns, 'types': types}
        except Exception:
            return {'columns': [], 'types': []}
    return {'columns': [], 'types': []}

from openpyxl import load_workbook

class FinalizeUploadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        temp_path         = request.data.get('temp_path')
        name              = request.data.get('name')
        original_filename = request.data.get('original_filename')
        file_type         = request.data.get('file_type')
        connection_id     = request.data.get('connection')
        sheet             = request.data.get('sheet')

        if not all([temp_path, name, original_filename, file_type]):
            return Response(
                {"error": "Необходимы поля temp_path, name, original_filename, file_type"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not os.path.exists(temp_path):
            return Response({"error": "Временный файл не найден"}, status=status.HTTP_404_NOT_FOUND)

        connection_obj = None
        if connection_id:
            try:
                connection_obj = Connection.objects.get(pk=connection_id)
            except Connection.DoesNotExist:
                return Response({"error": "Connection not found"}, status=404)

        upload = FileUpload(
            owner=request.user,
            name=name,
            original_filename=original_filename,
            file_type=file_type,
            connection=connection_obj
        )

        # Сначала сохраняем объект без файла
        upload.save()
        
        if file_type == "xlsx" and sheet:
            print(f"[DEBUG] Обрабатываем Excel файл с листом: {sheet}")
            try:
                wb = load_workbook(temp_path, read_only=False)
                print(f"[DEBUG] Доступные листы: {wb.sheetnames}")
                
                # Удаляем все листы кроме нужного
                sheets_to_remove = [ws_name for ws_name in wb.sheetnames if ws_name != sheet]
                for ws_name in sheets_to_remove:
                    ws = wb[ws_name]
                    wb.remove(ws)
                
                single_sheet_path = temp_path + "_single.xlsx"
                wb.save(single_sheet_path)
                wb.close()  # Явно закрываем workbook
                print(f"[DEBUG] Сохраняем одностраничный файл: {single_sheet_path}")
                
                with open(single_sheet_path, 'rb') as f:
                    upload.file.save(original_filename, File(f), save=True)  # save=True для сохранения в БД
                print(f"[DEBUG] Файл сохранен в базу: {upload.file.path}")
                
                try:
                    os.remove(single_sheet_path)
                except Exception as e:
                    print(f"[DEBUG] Ошибка при удалении временного файла: {e}")
                    
            except Exception as e:
                print(f"[DEBUG] Ошибка при обработке листов: {e}")
                # Если ошибка, сохраняем оригинальный файл
                with open(temp_path, 'rb') as f:
                    upload.file.save(original_filename, File(f), save=True)
        else:
            with open(temp_path, 'rb') as f:
                upload.file.save(original_filename, File(f), save=True)  # save=True для сохранения в БД

        upload.columns_info = extract_columns_info(upload)
        upload.save(update_fields=['columns_info'])

        try:
            os.remove(temp_path)
        except OSError:
            pass

        serializer = FileUploadSerializer(upload)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

# ==============================================================================
# XLSX helper endpoints
# ==============================================================================

class XlsxSheetListView(APIView):
    """
    POST /xlsx/sheets/   — получить список листов в загруженном .xlsx-файле
    """
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        file = request.FILES.get('file')
        if not file or not file.name.endswith('.xlsx'):
            raise ValidationError("Ожидался .xlsx файл")

        try:
            wb = load_workbook(filename=file, read_only=True)
            return Response({"filename": file.name, "sheets": wb.sheetnames})
        except Exception as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class XlsxTempPreviewView(APIView):
    """
    POST /xlsx/preview/  — предпросмотр содержимого временного .xlsx-файла
    Использует Celery для асинхронной обработки больших файлов с polars, чанкингом и векторизацией.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        temp_path     = request.data.get('temp_path')
        has_header    = request.data.get('has_header', 'true').lower() == 'true'
        sheet_name    = request.data.get('sheet_name')
        row_limit     = int(request.data.get('row_limit', 200))
        use_async     = request.data.get('async', 'false').lower() == 'true'

        if not temp_path or not os.path.exists(temp_path):
            return Response({"error": "Временный файл не найден"}, status=status.HTTP_404_NOT_FOUND)

        # Определяем размер файла для выбора стратегии
        file_size = os.path.getsize(temp_path)
        # Для файлов больше 5MB или при явном запросе используем асинхронную обработку
        should_use_async = use_async or file_size > 5 * 1024 * 1024 or row_limit > 500

        if should_use_async:
            from src.core.bi_analysis.tasks import process_file_preview
            task = process_file_preview.delay(temp_path, sheet_name, row_limit, has_header)
            return Response({
                "task_id": task.id,
                "status": "processing",
                "message": "Предпросмотр обрабатывается асинхронно"
            }, status=202)

        # Синхронная обработка для маленьких файлов
        try:
            # Пробуем использовать polars для быстрой обработки
            try:
                import polars as pl
                
                file_ext = os.path.splitext(temp_path)[1].lower()
                
                if file_ext in ('.xlsx', '.xls'):
                    if sheet_name:
                        df = pl.read_excel(temp_path, sheet_name=sheet_name)
                    else:
                        df = pl.read_excel(temp_path, sheet_index=0)
                    
                    if row_limit and row_limit > 0:
                        df = df.head(row_limit)
                    
                    columns = df.columns
                    rows_list = df.to_numpy().tolist()
                    
                    if has_header and rows_list:
                        parsed = [list(columns), *rows_list]
                    else:
                        parsed = rows_list
                    
                    return Response({"parsed": parsed})
                    
                elif file_ext in ('.csv', '.txt'):
                    try:
                        df = pl.read_csv(temp_path, encoding='utf8', try_parse_dates=True)
                    except:
                        df = pl.read_csv(temp_path, encoding='cp1251', try_parse_dates=True)
                    
                    if row_limit and row_limit > 0:
                        df = df.head(row_limit)
                    
                    columns = df.columns
                    rows_list = df.to_numpy().tolist()
                    
                    if has_header and rows_list:
                        parsed = [list(columns), *rows_list]
                    else:
                        parsed = rows_list
                    
                    return Response({"parsed": parsed})
            except ImportError:
                # Fallback на openpyxl если polars не установлен
                pass

            # Fallback на openpyxl
            wb = load_workbook(filename=temp_path, read_only=True, data_only=True)
            try:
                ws = wb.active
            except IndexError:
                wb.close()
                return Response({"parsed": []})

            rows = []
            for row in ws.iter_rows(values_only=True):
                normalized = [("" if cell is None else str(cell)) for cell in row]
                rows.append(normalized)
                if len(rows) >= row_limit:
                    break
            wb.close()

            if not rows:
                return Response({"parsed": []})

            if has_header:
                header, *body = rows
                parsed = [list(header), *body]
            else:
                parsed = rows

            return Response({"parsed": parsed})
        except Exception as exc:
            return Response({"error": f"Ошибка при чтении файла: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FilePreviewTaskStatusView(APIView):
    """
    GET /xlsx/preview/task-status/  — получение статуса задачи предпросмотра файла
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """
        Получает статус и результат асинхронной задачи предпросмотра файла.
        """
        task_id = request.query_params.get('task_id')
        if not task_id:
            return Response({"detail": "Не указан task_id"}, status=400)
        
        try:
            from celery.result import AsyncResult
            from src.config.celery import celery_app
            
            task = AsyncResult(task_id, app=celery_app)
            
            if task.state == 'PENDING':
                response = {
                    'task_id': task_id,
                    'status': 'pending',
                    'message': 'Задача ожидает выполнения'
                }
            elif task.state == 'PROGRESS':
                response = {
                    'task_id': task_id,
                    'status': 'processing',
                    'message': task.info.get('message', 'Задача выполняется') if isinstance(task.info, dict) else 'Задача выполняется',
                    'progress': task.info.get('progress', 0) if isinstance(task.info, dict) else None
                }
            elif task.state == 'SUCCESS':
                result = task.result
                response = {
                    'task_id': task_id,
                    'status': 'success',
                    'result': result
                }
            elif task.state == 'FAILURE':
                response = {
                    'task_id': task_id,
                    'status': 'failure',
                    'error': str(task.info) if task.info else 'Неизвестная ошибка'
                }
            else:
                response = {
                    'task_id': task_id,
                    'status': task.state.lower(),
                    'message': f'Статус задачи: {task.state}'
                }
            
            return Response(response, status=200)
            
        except Exception as e:
            return Response({"detail": f"Ошибка получения статуса задачи: {str(e)}"}, status=500)

# ==============================================================================
# Field values endpoint
# ==============================================================================

class DatasetFieldValuesView(APIView):
    """
    GET /bi_analysis/bi_datasets/{pk}/field-values/{field_id}/
    Получить уникальные значения для конкретного поля датасета
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, pk, field_id):
        dataset = Dataset.objects.filter(pk=pk, owner=request.user).first()
        
        if not dataset:
            dataset_exists = Dataset.objects.filter(pk=pk).exists()
            
            if dataset_exists:
                return Response({"detail": "Dataset exists but doesn't belong to current user"}, status=404)
            else:
                return Response({"detail": "Dataset not found"}, status=404)

        field = DataSetField.objects.filter(pk=field_id, dataset=dataset).first()
        
        if not field:
            field_exists = DataSetField.objects.filter(pk=field_id).exists()
            
            if field_exists:
                return Response({"detail": "Field exists but doesn't belong to this dataset"}, status=404)
            else:
                return Response({"detail": "Field not found"}, status=404)

        if not dataset.table_ref or not dataset.table_ref.startswith(('staging_', 'temp_')):
            return Response({"detail": "Таблица ещё не создана для датасета"}, status=400)

        base_table = dataset.table_ref
        if '.' in base_table:
            schema, table = base_table.split('.', 1)
        else:
            schema, table = 'public', base_table

        try:
            with connection.cursor() as cursor:
                # Get unique values for the field
                cursor.execute(
                    f'SELECT DISTINCT "{field.source_column}" FROM "{schema}"."{table}" WHERE "{field.source_column}" IS NOT NULL ORDER BY "{field.source_column}" LIMIT 1000',
                )
                rows = cursor.fetchall()
                values = [str(row[0]) for row in rows if row[0] is not None]
        except ProgrammingError:
            return Response({"detail": f"Table {schema}.{table} does not exist or field {field.source_column} not found"}, status=404)
        except Exception as e:
            return Response({"detail": f"Database error: {str(e)}"}, status=500)

        return Response({
            "field_id": field_id,
            "field_name": field.name,
            "field_column": field.source_column,
            "values": values,
            "count": len(values)
        })
