"""
Middleware для извлечения информации об организации из JWT токена.

Автоматически устанавливает request.organization и request.organization_id
для всех аутентифицированных запросов с organization_id в токене.

Примечание: Этот middleware безопасен для использования даже если модуль
organizations не установлен. В этом случае загрузка объекта организации
будет пропущена, но organization_id будет извлечён из токена.
"""

import logging

logger = logging.getLogger(__name__)

# Флаг доступности модуля organizations
_organizations_module_available = None


def is_organizations_module_available():
    """
    Проверяет, установлен ли модуль organizations.
    Результат кешируется для производительности.
    """
    global _organizations_module_available
    
    if _organizations_module_available is None:
        try:
            from src.modules.organizations.models import Organization
            _organizations_module_available = True
        except ImportError:
            _organizations_module_available = False
            logger.debug("Модуль organizations не установлен")
    
    return _organizations_module_available


class OrganizationMiddleware:
    """
    Middleware для обработки organization_id из JWT токена.
    
    Извлекает organization_id из payload JWT токена и устанавливает:
    - request.organization_id: ID организации или None
    - request.department_id: ID подразделения или None
    - request.organization: Объект организации (ленивая загрузка) или None
    
    Важно: Этот middleware должен быть размещён ПОСЛЕ AuthenticationMiddleware
    и ПОСЛЕ любого JWT authentication middleware.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
        # Кешируем модель Organization для избежания циклических импортов
        self._organization_model = None
    
    def __call__(self, request):
        # Инициализируем атрибуты по умолчанию
        request.organization_id = None
        request.department_id = None
        request._organization_cache = None
        
        # Пробуем извлечь organization_id из токена
        self._extract_organization_from_token(request)
        
        # Добавляем свойство для ленивой загрузки организации
        request.__class__.organization = property(
            lambda self: self._get_organization()
        )
        
        # Добавляем метод для загрузки организации
        request._get_organization = lambda: self._load_organization(request)
        
        response = self.get_response(request)
        return response
    
    def _extract_organization_from_token(self, request):
        """
        Извлекает organization_id и department_id из JWT токена.
        """
        # JWT token payload доступен через request.auth после JWTAuthentication
        if hasattr(request, 'auth') and request.auth:
            try:
                organization_id = request.auth.get('organization_id')
                department_id = request.auth.get('department_id')
                
                if organization_id is not None:
                    request.organization_id = int(organization_id)
                    
                if department_id is not None:
                    request.department_id = int(department_id)
                    
            except (ValueError, TypeError, AttributeError) as e:
                logger.warning(
                    f"Ошибка извлечения organization_id из токена: {e}"
                )
    
    def _load_organization(self, request):
        """
        Ленивая загрузка объекта организации.
        Возвращает None если модуль organizations не установлен.
        """
        if request._organization_cache is not None:
            return request._organization_cache
        
        if not request.organization_id:
            return None
        
        # Проверяем доступность модуля organizations
        if not is_organizations_module_available():
            return None
        
        try:
            # Ленивый импорт модели для избежания циклических зависимостей
            if self._organization_model is None:
                from src.modules.organizations.models import Organization
                self._organization_model = Organization
            
            organization = self._organization_model.objects.filter(
                id=request.organization_id,
                is_subdivision=False
            ).first()
            
            request._organization_cache = organization
            return organization
            
        except Exception as e:
            logger.warning(
                f"Ошибка загрузки организации {request.organization_id}: {e}"
            )
            return None


class OrganizationRequiredMiddleware:
    """
    Middleware для проверки наличия активной организации.
    
    Используется для endpoints, которые требуют активной организации.
    Возвращает 403 Forbidden если organization_id отсутствует в токене.
    
    Примечание: Этот middleware не добавляется глобально, а используется
    как декоратор для конкретных views через @method_decorator.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request):
        # Проверяем наличие organization_id
        if not getattr(request, 'organization_id', None):
            from rest_framework.response import Response
            from rest_framework import status
            
            return Response(
                {'error': 'Требуется активная организация. Выполните вход в организацию.'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        return self.get_response(request)
