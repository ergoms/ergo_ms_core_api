from django.contrib.contenttypes.models import ContentType
from ..models import LcpAuditLog


class AuditService:
    """Сервис для записи аудита"""
    
    @staticmethod
    def log_create(instance, user, request=None):
        """Записать создание объекта"""
        return AuditService._create_log(
            instance=instance,
            action='create',
            user=user,
            request=request,
            snapshot=AuditService._serialize_instance(instance)
        )
    
    @staticmethod
    def log_update(instance, user, changes, request=None):
        """Записать обновление объекта"""
        return AuditService._create_log(
            instance=instance,
            action='update',
            user=user,
            request=request,
            changes=changes,
            snapshot=AuditService._serialize_instance(instance)
        )
    
    @staticmethod
    def log_delete(instance, user, request=None):
        """Записать удаление объекта"""
        return AuditService._create_log(
            instance=instance,
            action='delete',
            user=user,
            request=request,
            snapshot=AuditService._serialize_instance(instance)
        )
    
    @staticmethod
    def log_publish(instance, user, request=None):
        """Записать публикацию"""
        return AuditService._create_log(
            instance=instance,
            action='publish',
            user=user,
            request=request
        )
    
    @staticmethod
    def log_revert(instance, user, target_log_id, request=None):
        """Записать откат к версии"""
        return AuditService._create_log(
            instance=instance,
            action='revert',
            user=user,
            request=request,
            metadata={'reverted_to': target_log_id}
        )
    
    @staticmethod
    def _create_log(instance, action, user, request=None, changes=None, snapshot=None, metadata=None):
        """Создать запись аудита"""
        content_type = ContentType.objects.get_for_model(instance)
        
        ip_address = None
        user_agent = ''
        
        if request:
            ip_address = AuditService._get_client_ip(request)
            user_agent = request.META.get('HTTP_USER_AGENT', '')[:500]
        
        return LcpAuditLog.objects.create(
            content_type=content_type,
            object_id=instance.pk,
            action=action,
            changes=changes or {},
            snapshot=snapshot,
            metadata=metadata or {},
            user=user,
            ip_address=ip_address,
            user_agent=user_agent
        )
    
    @staticmethod
    def _get_client_ip(request):
        """Получить IP клиента"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')
    
    @staticmethod
    def _serialize_instance(instance):
        """Сериализовать экземпляр для снимка"""
        if hasattr(instance, '__dict__'):
            data = {}
            for key, value in instance.__dict__.items():
                if not key.startswith('_'):
                    try:
                        # Проверяем сериализуемость
                        import json
                        json.dumps(value)
                        data[key] = value
                    except (TypeError, ValueError):
                        data[key] = str(value)
            return data
        return None
    
    @staticmethod
    def get_history(instance, limit=50):
        """Получить историю изменений объекта"""
        content_type = ContentType.objects.get_for_model(instance)
        return LcpAuditLog.objects.filter(
            content_type=content_type,
            object_id=instance.pk
        ).order_by('-timestamp')[:limit]


