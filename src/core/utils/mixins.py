from django.core.files.storage import default_storage
from rest_framework.exceptions import ValidationError


class SwaggerSafeMixin:
    """
    Миксин для безопасной работы с Swagger генерацией схемы.
    Предотвращает ошибки при генерации документации API.
    """
    
    def is_swagger_fake_view(self):
        """Проверяет, является ли текущий запрос фейковым для Swagger"""
        return getattr(self, 'swagger_fake_view', False)
    
    def get_safe_user(self):
        """Безопасно получает пользователя, учитывая Swagger контекст"""
        if self.is_swagger_fake_view():
            return None
        return self.request.user
    
    def get_safe_queryset(self, base_queryset):
        """Безопасно фильтрует queryset, учитывая Swagger контекст"""
        if self.is_swagger_fake_view():
            return base_queryset.none()
        return base_queryset


class MediaApiFileMixin:
    """
    Миксин для views, принимающих как прямой upload (request.FILES),
    так и путь к файлу, загруженному через media_api (file_path).

    Использование во view:
        file, file_path = self.get_file_or_path('file')
        if file:
            instance.file.save(file.name, file)
        elif file_path:
            instance.file.name = file_path
            instance.save()
    """

    def get_file_or_path(self, field_name='file'):
        """
        Возвращает (file, None) при прямой загрузке
        или (None, path) при загрузке через media_api.
        """
        file_path = self.request.data.get(f'{field_name}_path')
        if file_path:
            if not default_storage.exists(file_path):
                raise ValidationError({field_name: f'Файл не найден: {file_path}'})
            return None, file_path
        return self.request.FILES.get(field_name), None

    @staticmethod
    def assign_file_field(instance, field_name, file=None, file_path=None):
        """
        Присваивает файл или путь в FileField/ImageField.
        Если file — сохраняет через storage. Если file_path — ставит name напрямую.
        """
        field = getattr(instance, field_name)
        if file:
            field.save(file.name, file, save=False)
        elif file_path:
            field.name = file_path