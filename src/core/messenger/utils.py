from django.contrib.contenttypes.models import ContentType
from rest_framework.exceptions import ValidationError


def get_content_type(content_type_str):
    """Resolve ContentType from string. Supports 'app_label.model' or 'model' (requires unique model)."""
    try:
        if '.' in content_type_str:
            app_label, model = content_type_str.split('.', 1)
            return ContentType.objects.get_by_natural_key(app_label, model)
        qs = ContentType.objects.filter(model=content_type_str)
        if qs.count() > 1:
            raise ValidationError(
                f'Неоднозначный тип контента "{content_type_str}". '
                'Укажите в формате app_label.model (например: tasks.task)'
            )
        return qs.get()
    except ContentType.DoesNotExist:
        raise ValidationError(f'Тип контента "{content_type_str}" не найден')
