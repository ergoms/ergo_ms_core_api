from django.db import models
from django.contrib.auth import get_user_model
from src.core.bi_analysis.bi_connections.models import Connection
import uuid

JSONField = models.JSONField

TYPE_CHOICES = [
    ('geopolygon', 'Геополигон'),
    ('geopoint',   'Геоточка'),
    ('date',       'Дата'),
    ('date&time',  'Дата и время'),
    ('float',      'Дробное число'),
    ('bool',       'Логический'),
    ('string',     'Строка'),
    ('integer',    'Целое число'),
]

AGG_CHOICES = [
    ('none', 'Нет'),
    ('count', 'Количество'),
    ('ucount', 'Количество уникальных'),
    ('max',   'Максимум'),
    ('min',   'Минимум'),
    ('avg',   'Среднее'),
    ('sum',   'Сумма'),
]

class FileUpload(models.Model):
    name = models.CharField(max_length=255)
    connection = models.ForeignKey(Connection, null=True, blank=True, on_delete=models.CASCADE, related_name='files')
    file = models.FileField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    owner = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, related_name='uploaded_files')
    columns_info = models.JSONField(null=True, blank=True, default=dict)

    original_filename = models.CharField(max_length=255, blank=True, null=True)
    file_type = models.CharField(max_length=50, blank=True, null=True)
    file_uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # Генерируем UUID при первом сохранении, если его еще нет
        if not self.file_uuid:
            self.file_uuid = uuid.uuid4()
        super().save(*args, **kwargs)

class Dataset(models.Model):
    name        = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    owner       = models.ForeignKey(
        get_user_model(),
        on_delete=models.CASCADE,
        related_name='datasets'
    )
    file_source = models.ForeignKey(
        'bi_analysis_bi_datasets.FileUpload',
        null=True, blank=True,
        on_delete=models.SET_NULL
    )
    connection  = models.ForeignKey(
        Connection,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='datasets'
    )
    table_ref   = models.CharField(max_length=255, blank=True, null=True)
    params      = models.JSONField(null=True, blank=True, default=list)

    def fields_for_current_dataset(self):
        return self.fields.all()
    
    def __str__(self):
        return self.name

    # -----------------------------
    # Параметры датасета (work with DatasetParam)
    # -----------------------------
    def get_params_items(self):
        """Вернуть параметры как список словарей в стабильном порядке."""
        qs = getattr(self, 'params_items', None)
        if qs is None:
            return []
        return list(
            qs.order_by('order', 'id').values(
                'id', 'name', 'type', 'default_value', 'source_usage', 'order', 'description'
            )
        )

    def set_params_items(self, items):
        """
        Идемпотентно применяет список параметров к датасету.
        Формат items: [{name, type, default_value, source_usage, order, description}].
        Upsert по имени; отсутствующие — удаляются.
        """
        from django.db import transaction
        from .models import DatasetParam  # локальный импорт для избежания циклов

        items = items or []
        with transaction.atomic():
            existing = {p.name: p for p in self.params_items.all()}
            keep_names = set()

            for idx, raw in enumerate(items):
                name = (raw or {}).get('name')
                if not name:
                    continue
                keep_names.add(name)
                obj = existing.get(name) or DatasetParam(dataset=self, name=name)
                obj.type = raw.get('type') or obj.type or 'string'
                obj.default_value = raw.get('default_value') if 'default_value' in raw else obj.default_value
                obj.source_usage = bool(raw.get('source_usage', obj.source_usage))
                obj.order = raw.get('order', obj.order if obj.order is not None else idx)
                obj.description = raw.get('description', obj.description or "")
                obj.save()

            # Удаляем параметры, которых больше нет в items
            self.params_items.exclude(name__in=list(keep_names)).delete()

    def params_as_json(self):
        """
        Совместимость: получить параметры в JSON-формате как раньше в поле `params`.
        """
        return [
            {
                'name': p['name'],
                'type': p['type'],
                'default': p['default_value'],
                'sourceUsage': p['source_usage'],
            }
            for p in self.get_params_items()
        ]


class DataSetTable(models.Model):
    dataset    = models.ForeignKey(
        Dataset, related_name="tables", on_delete=models.CASCADE
    )
    connection = models.ForeignKey(
        Connection, related_name="dataset_tables", on_delete=models.CASCADE
    )

    table_name = models.CharField(max_length=200)
    alias      = models.CharField(max_length=100, blank=True)

    # ключ и порядок
    joined_on  = models.JSONField(default=dict)      # {type, left, right}
    order      = models.PositiveSmallIntegerField(default=0)

    # ← ОСТАВЛЯЕМ ровно ОДНО поле file_upload
    file_upload  = models.ForeignKey(
        FileUpload, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="dataset_tables"
    )

    # «человеческое» имя и схема колонок
    display_name = models.CharField(max_length=255, blank=True)
    columns_info = models.JSONField(null=True, blank=True)

    # --- новые атрибуты ---
    sheet_name       = models.CharField(max_length=255, blank=True, null=True)
    joined_on_type   = models.CharField(max_length=16,  blank=True, null=True)
    joined_on_left   = models.CharField(max_length=128, blank=True, null=True)
    joined_on_right  = models.CharField(max_length=128, blank=True, null=True)

    # ----------------------

    def save(self, *args, **kwargs):
        """Если таблица привязана к FileUpload — подтянуть имя и columns_info."""
        if self.file_upload_id:
            if not self.display_name:
                self.display_name = self.file_upload.original_filename

            if self.columns_info is None and self.file_upload.columns_info:
                self.columns_info = self.file_upload.columns_info

        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.dataset.name} → {self.table_name}"


class DataSetField(models.Model):
    dataset       = models.ForeignKey(
        Dataset,
        related_name="fields",
        on_delete=models.CASCADE
    )
    name          = models.CharField(max_length=200)
    source_table  = models.ForeignKey(
        DataSetTable,
        related_name="fields",
        on_delete=models.CASCADE
    )
    source_column = models.CharField(max_length=200) 
    expression    = models.TextField(blank=True)
    type          = models.CharField(
        max_length=20,
        choices=TYPE_CHOICES,
        default='string'
    )
    aggregation   = models.CharField(
        max_length=20,
        choices=AGG_CHOICES,
        default='none'
    )
    order         = models.PositiveSmallIntegerField(default=0)
    description   = models.TextField(blank=True, default="")

    def __str__(self):
        return f"{self.dataset.name}.{self.name}"


class DatasetParam(models.Model):
    """Отдельная сущность параметров датасета."""
    TYPE_CHOICES_SIMPLE = [
        ('string', 'Строка'),
        ('integer', 'Целое'),
        ('float', 'Дробное'),
        ('bool', 'Логический'),
        ('date', 'Дата'),
        ('date&time', 'Дата и время'),
    ]

    dataset = models.ForeignKey(
        Dataset, related_name='params_items', on_delete=models.CASCADE
    )
    name = models.CharField(max_length=200)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES_SIMPLE, default='string')
    default_value = JSONField(null=True, blank=True)
    source_usage = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['dataset', 'name']),
        ]

    def __str__(self) -> str:
        return f"{self.dataset_id}:{self.name}"