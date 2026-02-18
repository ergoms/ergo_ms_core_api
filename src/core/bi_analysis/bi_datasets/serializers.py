from rest_framework import serializers
from django.contrib.auth import get_user_model

from src.core.bi_analysis.bi_connections.models import Connection
from src.core.bi_analysis.bi_datasets.models import FileUpload, Dataset, DataSetTable, DataSetField, DatasetParam

import os
import openpyxl, csv

User = get_user_model()

# --- Короткие сериализаторы для списков/превью ---
class DataSetTableShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSetTable
        fields = ['id', 'table_name', 'alias']

class DataSetFieldShortSerializer(serializers.ModelSerializer):
    class Meta:
        model = DataSetField
        fields = ['id', 'name']

# --- Полные сериализаторы для detail ---
class DataSetTableSerializer(serializers.ModelSerializer):
    table_ref = serializers.SerializerMethodField()
    display_name = serializers.SerializerMethodField()
    file_upload_id = serializers.SerializerMethodField()
    file_upload_name = serializers.SerializerMethodField()
    joined_on = serializers.SerializerMethodField()
    joined_on_type = serializers.CharField()
    joined_on_left = serializers.CharField()
    joined_on_right = serializers.CharField()

    class Meta:
        model = DataSetTable
        fields = [
            'id', 'dataset', 'connection', 'table_name', 'alias',
            'joined_on', 'order', 'table_ref', 'display_name',
            'file_upload_id', 'file_upload_name', 'columns_info',
            'joined_on_type', 'joined_on_left', 'joined_on_right',
            'sheet_name'
        ]
        read_only_fields = ['id']
        
    def get_table_ref(self, obj):
        return obj.table_name
    
    def get_display_name(self, obj):
        if obj.display_name and not obj.display_name.startswith('temp_'):
            return obj.display_name

        if obj.file_upload and obj.sheet_name:
            filename = obj.file_upload.original_filename.replace('.xlsx', '')
            return f"{filename} – {obj.sheet_name}"
        elif obj.file_upload:
            return obj.file_upload.original_filename
        else:
            return obj.table_name

    def get_file_upload_id(self, obj):
        return obj.file_upload.id if obj.file_upload else None

    def get_file_upload_name(self, obj):
        return obj.file_upload.original_filename if obj.file_upload else None

    def get_joined_on(self, obj):
        if obj.joined_on_type:
            return {
                "type": obj.joined_on_type,
                "left_column": obj.joined_on_left,
                "right_column": obj.joined_on_right,
            }
        return None

class DataSetFieldSerializer(serializers.ModelSerializer):
    source_table_name = serializers.SerializerMethodField()
    category = serializers.ReadOnlyField()

    class Meta:
        model = DataSetField
        fields = [
            'id', 'dataset', 'name',
            'source_table', 'source_table_name',
            'source_column', 'expression', 'type',
            'aggregation', 'order', 'description', 'category'
        ]
        read_only_fields = ['id', 'source_table',
        'source_column', 'expression', 'order', 'source_table_name', 'category']

    def get_source_table_name(self, obj):
        return obj.source_table.table_name if obj.source_table else None

class DatasetUpdateSerializer(serializers.ModelSerializer):
    fields = DataSetFieldSerializer(many=True, required=False)
    params = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model  = Dataset
        fields = ['id', 'name', 'description', "connection", 'fields', 'params']
        read_only_fields = ['id', 'connection']

    def update(self, instance, validated_data):
        non_nested = {k: v for k, v in validated_data.items() if k not in ('fields', 'params')}
        instance = super().update(instance, non_nested)

        params_data = self.initial_data.get('params', None)
        if params_data is not None:
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
            instance.set_params_items(items)
        # ВАЖНО: используем default=None, чтобы отличать
        # "ключ fields не передан" (fields_data is None)
        # от "передан пустой список" (fields_data == []).
        fields_data = self.initial_data.get('fields', None)
        if fields_data is not None:  # Ключ fields явно присутствует (может быть пустым списком)
            raw_ids = [field_data.get('id') for field_data in fields_data if field_data.get('id') is not None]
            field_ids_in_request = set()
            for fid in raw_ids:
                try:
                    field_ids_in_request.add(int(fid))
                except (TypeError, ValueError):
                    pass

            # Удаляем поля, которых нет в запросе
            fields_to_delete = instance.fields.exclude(id__in=field_ids_in_request)
            if fields_to_delete.exists():
                fields_to_delete.delete()

            # Обновляем существующие поля и создаем новые
            for idx, field_data in enumerate(fields_data):
                raw_field_id = field_data.get('id')
                field_id = None
                if raw_field_id is not None:
                    try:
                        field_id = int(raw_field_id)
                    except (TypeError, ValueError):
                        pass
                if field_id:
                    # Обновляем существующее поле
                    field_obj = instance.fields.filter(id=field_id).first()
                    if field_obj:
                        update_fields = []
                        for attr in ['name', 'aggregation', 'type', 'description', 'expression']:
                            if attr in field_data:
                                val = field_data[attr]
                                if attr == 'expression':
                                    val = (val or '').strip() if val is not None else ''
                                setattr(field_obj, attr, val)
                                update_fields.append(attr)
                        if 'order' in field_data:
                            field_obj.order = field_data['order']
                            update_fields.append('order')
                        if update_fields:
                            field_obj.save(update_fields=update_fields)
                else:
                    # Создаем новое поле, если его нет
                    # Для создания нужны name и source_table (для поля с формулой source_column может быть пустым)
                    if field_data.get('name'):
                        source_table_data = field_data.get('source_table')
                        source_table_id = None
                        if isinstance(source_table_data, int):
                            source_table_id = source_table_data
                        elif isinstance(source_table_data, dict) and source_table_data and 'id' in source_table_data:
                            source_table_id = source_table_data['id']
                        if not source_table_id and instance.tables.exists():
                            source_table_id = instance.tables.filter(order=0).values_list('id', flat=True).first()
                        if source_table_id:
                            expr = (field_data.get('expression') or '').strip()
                            source_col = field_data.get('source_column') or ''
                            if expr and not source_col:
                                source_col = field_data.get('name', '')
                            DataSetField.objects.create(
                                dataset=instance,
                                name=field_data.get('name'),
                                aggregation=field_data.get('aggregation', 'none'),
                                type=field_data.get('type', 'string'),
                                description=field_data.get('description', ''),
                                source_column=source_col,
                                source_table_id=source_table_id,
                                expression=expr,
                                order=field_data.get('order', idx)
                            )
        field_names = set(instance.fields.values_list('name', flat=True))
        param_names = set()
        for p in (instance.get_params_items() or []):
            name = p.get('name') if isinstance(p, dict) else None
            if name:
                param_names.add(str(name).strip())
        overlap = field_names & param_names
        if overlap:
            raise serializers.ValidationError(
                {'non_field_errors': [f"Имена полей и параметров не должны совпадать: {', '.join(sorted(overlap))}."]}
            )
        return instance
    
class DatasetDetailSerializer(serializers.ModelSerializer):
    tables = DataSetTableSerializer(many=True, read_only=True)
    fields = DataSetFieldSerializer(many=True, read_only=True)
    params = serializers.JSONField(required=False, allow_null=True)

    class Meta:
        model = Dataset
        fields = [
            'id',
            'name',
            'description',
            'created_at',
            'tables',
            'fields',
            'params',
        ]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            data['params'] = instance.params_as_json()
        except Exception:
            pass
        return data

# --- Detail сериализаторы ---
class DatasetDetailFullSerializer(serializers.ModelSerializer):
    tables  = DataSetTableSerializer(many=True, read_only=True)
    fields  = DataSetFieldSerializer(many=True, read_only=True)
    params = serializers.JSONField(required=False, allow_null=True)
    class Meta:
        model  = Dataset
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            data['params'] = instance.params_as_json()
        except Exception:
            pass
        return data

# --- Для списка (list) ---
class DatasetShortSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    storage_type   = serializers.SerializerMethodField()

    def get_storage_type(self, obj):
        return 'postgres'

    class Meta:
        model  = Dataset
        fields = ['id', 'name', 'owner_username',
                  'storage_type', 'created_at']

# --- Для create/update ---
class DatasetSerializer(serializers.ModelSerializer):
    tables = DataSetTableSerializer(many=True, read_only=True)
    fields = DataSetFieldSerializer(many=True, read_only=True)
    params = serializers.JSONField(required=False, allow_null=True)

    owner = serializers.PrimaryKeyRelatedField(
        read_only=True,
        default=serializers.CurrentUserDefault()
    )

    file_source = serializers.PrimaryKeyRelatedField(
        queryset=FileUpload.objects.all(),
        write_only=True,
        required=False,
        allow_null=True
    )

    class Meta:
        model = Dataset
        fields = [
            'id',
            'name',
            'description',
            'created_at',
            'owner',
            'connection',
            'file_source',
            'table_ref',
            'tables',
            'fields',
            'params',
        ]
        read_only_fields = ['id', 'created_at', 'owner']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        try:
            data['params'] = instance.params_as_json()
        except Exception:
            pass
        return data


class DatasetParamSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatasetParam
        fields = ['id', 'dataset', 'name', 'type', 'default_value', 'source_usage', 'order', 'description', 'created_at']
        read_only_fields = ['id', 'created_at']

# --- File upload сериализатор ---
class FileUploadSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    file_path = serializers.SerializerMethodField()
    exists = serializers.SerializerMethodField()
    missing = serializers.SerializerMethodField()
    file_not_found = serializers.SerializerMethodField()
    error = serializers.SerializerMethodField()

    class Meta:
        model = FileUpload
        fields = [
            'id', 'name', 'file', 'file_url', 'file_path', 'uploaded_at',
            'owner', 'original_filename', 'file_type', 'connection', 'columns_info',
            'file_uuid', 'exists', 'missing', 'file_not_found', 'error'
        ]
        read_only_fields = ['id', 'uploaded_at', 'file_uuid']
        extra_kwargs = {
            'owner': {'read_only': True},
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Кэш для проверки существования файлов в рамках одного запроса
        self._file_exists_cache = {}

    def get_file_url(self, obj):
        try:
            return obj.file.url if obj.file else None
        except ValueError:
            return None
    
    def get_file_path(self, obj):
        """Возвращает путь к файлу"""
        try:
            return obj.file.path if obj.file else None
        except ValueError:
            return None
    
    def get_exists(self, obj):
        """Проверяет существование файла на диске с кэшированием"""
        # Используем id файла как ключ кэша
        cache_key = obj.id if obj.id else id(obj)
        
        if cache_key not in self._file_exists_cache:
            try:
                if obj.file and hasattr(obj.file, 'path'):
                    file_path = obj.file.path
                    # Кэшируем результат проверки
                    self._file_exists_cache[cache_key] = os.path.exists(file_path)
                else:
                    self._file_exists_cache[cache_key] = False
            except (ValueError, AttributeError):
                self._file_exists_cache[cache_key] = False
        
        return self._file_exists_cache[cache_key]
    
    def get_missing(self, obj):
        """Возвращает True если файл отсутствует"""
        return not self.get_exists(obj)
    
    def get_file_not_found(self, obj):
        """Alias для missing для совместимости"""
        return self.get_missing(obj)
    
    def get_error(self, obj):
        """Возвращает текст ошибки если файл отсутствует"""
        if self.get_missing(obj):
            return "Файл не найден на диске"
        return None