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

    class Meta:
        model = DataSetField
        fields = [
            'id', 'dataset', 'name',
            'source_table', 'source_table_name',
            'source_column', 'expression', 'type',
            'aggregation', 'order', 'description'
        ]
        read_only_fields = ['id', 'source_table',
        'source_column', 'expression', 'order', 'source_table_name']

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
        fields_data = self.initial_data.get('fields', [])
        if fields_data:
            for field_data in fields_data:
                field_obj = instance.fields.filter(id=field_data.get('id')).first()
                if field_obj:
                    for attr in ['name', 'aggregation', 'type', 'description']:
                        if attr in field_data:
                            setattr(field_obj, attr, field_data[attr])
                    field_obj.save(update_fields=['name', 'aggregation', 'type', 'description'])
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