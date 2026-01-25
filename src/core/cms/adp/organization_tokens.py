"""
Кастомные JWT токены с поддержкой organization_id.

Позволяют добавлять идентификатор организации в payload токена,
что обеспечивает серверную авторизацию в организацию по аналогии
с авторизацией пользователя.
"""

from rest_framework_simplejwt.tokens import RefreshToken, AccessToken
from datetime import timedelta


class OrganizationRefreshToken(RefreshToken):
    """
    Кастомный RefreshToken с поддержкой organization_id.
    
    Используется для создания токенов при входе в организацию.
    organization_id добавляется в payload токена и наследуется access токеном.
    """
    
    @classmethod
    def for_user_and_organization(cls, user, organization_id=None, department_id=None):
        """
        Создает refresh токен для пользователя с привязкой к организации.
        
        Args:
            user: Пользователь Django
            organization_id: ID организации (опционально)
            department_id: ID подразделения (опционально)
            
        Returns:
            OrganizationRefreshToken с organization_id в payload
        """
        token = cls.for_user(user)
        
        if organization_id is not None:
            token['organization_id'] = organization_id
            
        if department_id is not None:
            token['department_id'] = department_id
            
        return token
    
    @classmethod
    def for_user_without_organization(cls, user):
        """
        Создает refresh токен для пользователя без привязки к организации.
        Используется для выхода из организации.
        
        Args:
            user: Пользователь Django
            
        Returns:
            OrganizationRefreshToken без organization_id в payload
        """
        return cls.for_user(user)


def create_organization_tokens(user, organization_id=None, department_id=None, 
                                access_lifetime=None, refresh_lifetime=None):
    """
    Создает пару токенов (access, refresh) с organization_id.
    
    Args:
        user: Пользователь Django
        organization_id: ID организации (опционально)
        department_id: ID подразделения (опционально)
        access_lifetime: Время жизни access токена (timedelta)
        refresh_lifetime: Время жизни refresh токена (timedelta)
        
    Returns:
        dict: {'access': str, 'refresh': str}
    """
    refresh = OrganizationRefreshToken.for_user_and_organization(
        user, 
        organization_id=organization_id,
        department_id=department_id
    )
    
    if refresh_lifetime:
        refresh.set_exp(lifetime=refresh_lifetime)
    
    access = refresh.access_token
    
    if access_lifetime:
        access.set_exp(lifetime=access_lifetime)
    
    return {
        'access': str(access),
        'refresh': str(refresh)
    }


def get_organization_from_token(token_payload):
    """
    Извлекает organization_id из payload токена.
    
    Args:
        token_payload: dict с данными токена
        
    Returns:
        int или None: ID организации
    """
    if not token_payload:
        return None
    return token_payload.get('organization_id')


def get_department_from_token(token_payload):
    """
    Извлекает department_id из payload токена.
    
    Args:
        token_payload: dict с данными токена
        
    Returns:
        int или None: ID подразделения
    """
    if not token_payload:
        return None
    return token_payload.get('department_id')
