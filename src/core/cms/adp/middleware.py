"""
Middleware для проверки прав доступа к URL на основе политик.
"""
from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin
from src.core.cms.adp.services.permissions import PermissionService


class URLPermissionMiddleware(MiddlewareMixin):
    """
    Middleware для проверки доступа пользователей к URL.
    
    Проверяет права доступа на основе политик, определенных в системе.
    Администраторы имеют доступ ко всем URL.
    """
    
    # URL, которые не требуют проверки прав
    EXCLUDED_URLS = [
        '/api/adp/login/',
        '/api/adp/register/',
        '/api/adp/password-reset/',
        '/api/adp/verify-code/',
        '/api/adp/send-confirmation/',
        '/admin/',
        '/static/',
        '/media/',
    ]
    
    def process_request(self, request):
        """
        Проверяет права доступа перед обработкой запроса.
        """
        # Пропускаем неаутентифицированных пользователей
        if not request.user.is_authenticated:
            return None
        
        # Проверяем, нужно ли проверять этот URL
        url_path = request.path
        
        for excluded in self.EXCLUDED_URLS:
            if url_path.startswith(excluded):
                return None
        
        # Проверяем доступ
        has_access = PermissionService.check_url_access(request.user, url_path)
        
        if not has_access:
            return JsonResponse({
                'error': 'Access denied',
                'message': 'У вас нет прав доступа к этому ресурсу',
                'url': url_path
            }, status=403)
        
        return None
