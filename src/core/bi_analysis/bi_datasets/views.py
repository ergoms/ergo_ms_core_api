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
import pandas as pd
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
    auto_join_table,
    introspect_columns,
    rebuild_dataset_joins
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

        staging_name = import_file_upload_to_table(dataset.file_source.id)

        dataset.table_ref = staging_name
        dataset.save(update_fields=['table_ref'])

        temp_name = create_temp_table_from_source(dataset)
        dataset.table_ref = temp_name
        dataset.save(update_fields=['table_ref'])

        main_table = DataSetTable.objects.create(
            dataset=dataset,
            connection=dataset.connection,
            table_name=temp_name,
            joined_on={},
            file_upload=dataset.file_source 
        )
        
        if dataset.file_source and dataset.file_source.columns_info:
            main_table.columns_info = dataset.file_source.columns_info
            main_table.save(update_fields=["display_name", "columns_info"])

        populate_initial_fields(dataset, temp_name, staging_table=main_table)
        
        fields_data = self.request.data.get('fields', [])
        if fields_data:
            for field in fields_data:
                obj = dataset.fields.filter(name=field.get('name')).first()
                if obj and 'aggregation' in field:
                    obj.aggregation = field['aggregation']
                    obj.save(update_fields=['aggregation'])
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

        staging_name = import_file_upload_to_table(file_upload.id)

        from ..services.services import create_temp_table_from_staging
        temp_name = create_temp_table_from_staging(staging_name)

        data_table = DataSetTable.objects.create(
            dataset=dataset,
            connection=connection,
            table_name=temp_name,
            joined_on={},
            file_upload=file_upload
        )

        return Response({
            "id": data_table.id,
            "table_ref": data_table.table_name,
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
        print(f"[PREVIEW] dataset.id={dataset.id}, table_ref={dataset.table_ref}")
        if not dataset:
            return Response({"detail": "Not found"}, status=404)

        limit = int(request.query_params.get('limit', 10))
        if not dataset.table_ref or not dataset.table_ref.startswith(('staging_', 'temp_')):
            return Response({"detail": "Таблица ещё не создана для датасета"}, status=400)
        base_table = dataset.table_ref

        if '.' in base_table:
            schema, table = base_table.split('.', 1)
        else:
            schema, table = 'public', base_table

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT * FROM "{schema}"."{table}" LIMIT %s',
                    [limit],
                )
                rows = cursor.fetchall()
                columns = [col[0] for col in cursor.description]
        except ProgrammingError:
            return Response({"detail": f"Table {schema}.{table} does not exist"}, status=404)

        return Response({
            "columns": columns,
            "rows": rows
        })

class DatasetColumnsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        dataset = Dataset.objects.filter(pk=pk, owner=request.user).first()
        if not dataset:
            return Response({"detail": "Dataset not found"}, status=404)

        if not dataset.table_ref or not dataset.table_ref.startswith(("staging_", "temp_")):
            return Response({"detail": "Таблица ещё не создана для датасета"}, status=400)

        base_table = dataset.table_ref
        if "." in base_table:
            schema, table = base_table.split(".", 1)
        else:
            schema, table = "public", base_table

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    f'SELECT * FROM "{schema}"."{table}" LIMIT 0'
                )
                columns = [col[0] for col in cursor.description]
        except ProgrammingError:
            return Response({"detail": f"Table {schema}.{table} does not exist"}, status=404)

        return Response({"columns": columns})

class DatasetDraftPreviewView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        """
        Принимает черновик датасета (главная таблица + join'ы), возвращает предпросмотр данных.
        """
        data = request.data
        connection_id = data.get('connection_id')
        main_table    = data.get('mainTable')
        joined_tables = data.get('joinedTables', [])
        limit         = int(data.get('limit', 20))

        # 1. Импортируем главную таблицу во временную (если надо)
        staging_tables = {}

        def import_table(tbl):
            if 'file_id' in tbl:
                # из FileUpload
                return import_file_upload_to_table(tbl['file_id'])
            elif 'table_name' in tbl:
                return tbl['table_name']
            else:
                raise ValidationError("Не удалось определить источник таблицы")

        main_staging = import_table(main_table)
        staging_tables['main'] = main_staging

        # 2. Импортируем все joinedTables
        joined_stagings = []
        for jt in joined_tables:
            staging = import_table(jt)
            joined_stagings.append({
                **jt, 'staging': staging
            })

        # 3. Формируем SELECT и JOIN'ы
        select_sql = []
        main_alias = 'a'
        main_cols = introspect_columns(main_staging)
        select_sql += [f'{main_alias}."{col}" AS "{col}"' for col in main_cols]
        join_clauses = []
        alias = ord('b')

        for jt in joined_stagings:
            tbl_alias = chr(alias)
            cols = introspect_columns(jt['staging'])
            select_sql += [f'{tbl_alias}."{col}" AS "{col}"' for col in cols if col not in main_cols]

            # LEFT JOIN "staging" b ON a."left_col" = b."right_col"
            join_type = jt.get('joinType', 'LEFT JOIN').strip().upper()
            if not join_type.endswith('JOIN'):
                join_type += ' JOIN'
            lines = jt.get('lines') or []
            if not lines or not lines[0].get('left') or not lines[0].get('right'):
                raise ValidationError("Не указаны поля для join'а")
            left_col = lines[0]['left']
            right_col = lines[0]['right']
            join_clause = f"{join_type} \"{jt['staging']}\" {tbl_alias} ON {main_alias}.\"{left_col}\" = {tbl_alias}.\"{right_col}\""
            join_clauses.append(join_clause)
            alias += 1

        sql = f'SELECT {", ".join(select_sql)} FROM "{main_staging}" {main_alias} ' + " ".join(join_clauses) + f' LIMIT {limit}'

        with connection.cursor() as cursor:
            cursor.execute(sql)
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
        print(f"!!! QUERY PARAM dataset={dataset_id}")
        queryset = DataSetField.objects.all()
        if dataset_id:
            queryset = queryset.filter(dataset_id=dataset_id)
        print(f"!!! RESULT COUNT={queryset.count()}")
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
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        temp_path     = request.data.get('temp_path')
        has_header    = request.data.get('has_header', 'true').lower() == 'true'

        if not temp_path or not os.path.exists(temp_path):
            return Response({"error": "Временный файл не найден"}, status=status.HTTP_404_NOT_FOUND)

        try:
            df     = pd.read_excel(temp_path, header=0 if has_header else None)
            values = df.fillna('').astype(str).values.tolist()
            if has_header:
                values.insert(0, list(df.columns))
            return Response({"parsed": values})
        except Exception as exc:
            return Response({"error": f"Ошибка при чтении Excel: {exc}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
