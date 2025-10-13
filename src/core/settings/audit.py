from django.contrib.contenttypes.models import ContentType
from .models import AuditLog

def log_audit(request, instance, action, changes=None):
    """
    request — DRF Request (чтобы взять request.user),
    instance — сам объект модели,
    action — 'UPDATE' или 'DELETE',
    changes — dict diff полей (для UPDATE) или None.
    """
    AuditLog.objects.create(
        content_type = ContentType.objects.get_for_model(instance.__class__),
        object_id    = instance.pk,
        action       = action,
        changes      = changes,
        user         = request.user if request.user.is_authenticated else None,
    )