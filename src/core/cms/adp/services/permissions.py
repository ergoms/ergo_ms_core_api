"""
Сервис для проверки прав доступа пользователей к ресурсам системы.
"""
import re
from typing import List, Dict, Optional, Callable
from django.contrib.auth.models import User
from src.core.cms.adp.models import Role, RoleGroup, Policy, UserRole, ModulePermission


# Реестр хуков для расширения проверки прав модулями
# Ключ: имя хука, Значение: список callable
_permission_hooks: Dict[str, List[Callable]] = {
    'check_module_permission': [],  # Хуки для проверки прав модулей
}


def register_permission_hook(hook_name: str, callback: Callable):
    """
    Зарегистрировать хук для расширения проверки прав.
    
    Модули могут регистрировать свои хуки для добавления
    дополнительной логики проверки прав.
    
    Args:
        hook_name: Имя хука ('check_module_permission')
        callback: Функция-обработчик
        
    Сигнатура callback для 'check_module_permission':
        def callback(user, module_name, permission_key, **kwargs) -> Optional[bool]
        - Возвращает True если доступ разрешён
        - Возвращает False если доступ запрещён
        - Возвращает None если хук не применим (продолжить проверку)
    """
    if hook_name not in _permission_hooks:
        _permission_hooks[hook_name] = []
    
    if callback not in _permission_hooks[hook_name]:
        _permission_hooks[hook_name].append(callback)


def unregister_permission_hook(hook_name: str, callback: Callable):
    """Удалить хук из реестра."""
    if hook_name in _permission_hooks and callback in _permission_hooks[hook_name]:
        _permission_hooks[hook_name].remove(callback)


class PermissionService:
    """
    Сервис для работы с правами доступа пользователей.
    
    Поддерживает расширение через хуки — модули могут регистрировать
    свои обработчики для добавления контекстной логики проверки прав.
    """
    DEFAULT_ROLE_NAME = 'Пользователь'
    DEFAULT_ROLE_DESCRIPTION = 'Роль по умолчанию для всех пользователей'
    ADMIN_ROLE_NAME = 'Администратор'
    ADMIN_ROLE_DESCRIPTION = 'Системная роль с полным доступом'
    
    @staticmethod
    def get_user_role(user: User) -> Optional[UserRole]:
        """Получить активную роль пользователя"""
        user_role = UserRole.objects.select_related('role').filter(
            user=user,
            is_active=True
        ).first()
        
        if user_role:
            PermissionService._sync_user_admin_flag(
                user,
                PermissionService._is_admin_role(user_role.role)
            )
            return user_role
        
        # Если у пользователя нет активной роли - назначаем роль по умолчанию
        return PermissionService.assign_default_role(user)

    @staticmethod
    def _get_or_create_role_safe(name: str, description: str, is_system: bool) -> Role:
        """
        Безопасно получает или создаёт роль.
        Обрабатывает ситуацию, когда Group с таким именем уже существует,
        но Role ещё не создана.
        """
        from django.contrib.auth.models import Group
        from django.db import connection
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Сначала пробуем найти существующую Role
            return Role.objects.get(name=name)
        except Role.DoesNotExist:
            pass
        
        try:
            # Проверяем, есть ли Group с таким именем
            group = Group.objects.filter(name=name).first()
            
            if group:
                # Group существует, но Role нет - создаём Role через SQL
                with connection.cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO cms_adp_role (group_ptr_id, description, is_system, created_at, updated_at)
                        VALUES (%s, %s, %s, NOW(), NOW())
                        ON CONFLICT (group_ptr_id) DO NOTHING
                    """, [group.id, description, is_system])
                
                # Получаем созданную Role
                return Role.objects.get(name=name)
            else:
                # Group не существует - создаём Role обычным способом
                role = Role.objects.create(
                    name=name,
                    description=description,
                    is_system=is_system
                )
                return role
        except Exception as e:
            logger.error(
                f"Не удалось получить или создать роль '{name}'. "
                f"Убедитесь, что миграции применены. Ошибка: {e}",
                exc_info=True
            )
            raise

    @staticmethod
    def _get_or_create_default_role() -> Role:
        return PermissionService._get_or_create_role_safe(
            name=PermissionService.DEFAULT_ROLE_NAME,
            description=PermissionService.DEFAULT_ROLE_DESCRIPTION,
            is_system=True
        )

    @staticmethod
    def _get_or_create_admin_role() -> Role:
        return PermissionService._get_or_create_role_safe(
            name=PermissionService.ADMIN_ROLE_NAME,
            description=PermissionService.ADMIN_ROLE_DESCRIPTION,
            is_system=True
        )

    @staticmethod
    def _is_admin_role(role: Role) -> bool:
        """Определяет, относится ли роль к административным."""
        if not role:
            return False
        return role.role_type == 'admin'

    @staticmethod
    def _sync_user_admin_flag(user: User, should_be_admin: bool):
        """
        Синхронизирует значение django-поля is_staff пользователя с назначенной ролью.
        """
        if not getattr(user, 'pk', None):
            return
        
        current_is_staff = getattr(user, 'is_staff', False)
        if current_is_staff != should_be_admin:
            user.is_staff = should_be_admin
            user.save(update_fields=['is_staff'])

    @staticmethod
    def ensure_system_roles():
        """Гарантирует наличие базовых системных ролей."""
        # Создаём или обновляем роль "Пользователь" - делаем её системной
        default_role = PermissionService._get_or_create_default_role()
        if not default_role.is_system:
            default_role.is_system = True
            default_role.save(update_fields=['is_system'])
        
        # Создаём или обновляем роль "Администратор" - делаем её системной
        admin_role = PermissionService._get_or_create_admin_role()
        if not admin_role.is_system:
            admin_role.is_system = True
            admin_role.save(update_fields=['is_system'])

    @staticmethod
    def assign_default_role(user: User) -> UserRole:
        """Назначить пользователю роль по умолчанию"""
        default_role = PermissionService._get_or_create_default_role()
        user_role, created = UserRole.objects.get_or_create(
            user=user,
            role=default_role,
            defaults={'is_active': True}
        )
        if not created and not user_role.is_active:
            user_role.is_active = True
            user_role.save(update_fields=['is_active'])
        PermissionService._sync_user_admin_flag(user, False)
        return user_role
    
    @staticmethod
    def is_admin(user: User) -> bool:
        """Проверить, является ли пользователь администратором"""
        if getattr(user, 'is_superuser', False):
            return True
        
        if getattr(user, 'is_staff', False):
            return True
        
        user_role = PermissionService.get_user_role(user)
        if user_role and PermissionService._is_admin_role(user_role.role):
            return True
        
        return False
    
    @staticmethod
    def check_url_access(user: User, url_path: str) -> bool:
        """
        Проверить доступ пользователя к URL.
        
        Иерархия прав:
        1. Администратор → полный доступ ко всему
        2. Пользователь (базовая роль) → доступ разрешён по умолчанию
        3. Ролевые группы → могут ограничивать (deny) или явно разрешать (allow) доступ
        4. Политики применяются по приоритету (высший приоритет побеждает)
        
        Args:
            user: Пользователь
            url_path: Путь URL для проверки
            
        Returns:
            True если доступ разрешен, False если запрещен
        """
        # Администраторы имеют доступ ко всем URL
        if PermissionService.is_admin(user):
            return True
        
        # Получаем роль пользователя (автоматически назначается "Пользователь" если нет)
        user_role = PermissionService.get_user_role(user)
        if not user_role:
            # Этого не должно происходить, т.к. get_user_role назначает роль по умолчанию
            return False
        
        # Собираем все политики для роли и групп пользователя
        policies = []
        
        # Политики базовой роли (например, "Пользователь")
        role_policies = Policy.objects.filter(
            role=user_role.role,
            policy_type='url',
            is_active=True
        ).order_by('-priority')
        policies.extend(role_policies)
        
        # Политики ролевых групп (переопределяют базовые права)
        role_groups = user_role.role_groups.filter(is_active=True)
        for group in role_groups:
            group_policies = Policy.objects.filter(
                role_group=group,
                policy_type='url',
                is_active=True
            ).order_by('-priority')
            policies.extend(group_policies)
        
        # Проверяем политики по приоритету (высший приоритет первый)
        for policy in sorted(policies, key=lambda p: p.priority, reverse=True):
            if PermissionService._match_url_pattern(url_path, policy.resource_path, policy.is_pattern):
                # Найдено совпадение — возвращаем результат политики
                return policy.action == 'allow'
        
        # Если не найдено подходящих политик:
        # Для роли "Пользователь" — разрешаем доступ по умолчанию (базовый просмотр)
        # Это обеспечивает концепцию "пользователь видит всё, группы ограничивают"
        if user_role.role.name == PermissionService.DEFAULT_ROLE_NAME:
            return True
        
        # Для других ролей — запрещаем по умолчанию
        return False
    
    @staticmethod
    def _match_url_pattern(url_path: str, pattern: str, is_pattern: bool) -> bool:
        """
        Проверить соответствие URL шаблону.
        
        Args:
            url_path: Проверяемый URL
            pattern: Шаблон для сравнения
            is_pattern: Использовать ли wildcards
            
        Returns:
            True если URL соответствует шаблону
        """
        if not is_pattern:
            # Точное совпадение
            return url_path == pattern
        
        # Преобразуем wildcard шаблон в regex
        # * заменяется на [^/]+ (любые символы кроме /)
        # ** заменяется на .* (любые символы)
        regex_pattern = pattern.replace('**', '<<<DOUBLE_STAR>>>') \
                               .replace('*', '[^/]+') \
                               .replace('<<<DOUBLE_STAR>>>', '.*')
        regex_pattern = f'^{regex_pattern}$'
        
        return bool(re.match(regex_pattern, url_path))
    
    @staticmethod
    def get_user_permissions(user: User) -> Dict:
        """
        Получить все права пользователя.
        
        Returns:
            Словарь с информацией о правах пользователя
        """
        user_role = PermissionService.get_user_role(user)
        
        if not user_role:
            return {
                'user_id': user.id,
                'username': user.username,
                'role': None,
                'role_groups': [],
                'allowed_urls': [],
                'denied_urls': [],
                'module_permissions': []
            }
        
        # Собираем разрешенные и запрещенные URL
        allowed_urls = []
        denied_urls = []
        
        # Политики роли
        role_policies = Policy.objects.filter(
            role=user_role.role,
            policy_type='url',
            is_active=True
        )
        
        for policy in role_policies:
            if policy.action == 'allow':
                allowed_urls.append(policy.resource_path)
            else:
                denied_urls.append(policy.resource_path)
        
        # Политики ролевых групп
        role_groups = user_role.role_groups.filter(is_active=True)
        for group in role_groups:
            group_policies = Policy.objects.filter(
                role_group=group,
                policy_type='url',
                is_active=True
            )
            
            for policy in group_policies:
                if policy.action == 'allow':
                    allowed_urls.append(policy.resource_path)
                else:
                    denied_urls.append(policy.resource_path)
        
        # Собираем права модулей
        module_permissions = []
        for group in role_groups:
            perms = ModulePermission.objects.filter(
                role_group=group,
                is_granted=True
            )
            module_permissions.extend(perms)
        
        return {
            'user_id': user.id,
            'username': user.username,
            'role': user_role.role,
            'role_groups': list(role_groups),
            'allowed_urls': allowed_urls,
            'denied_urls': denied_urls,
            'module_permissions': module_permissions
        }
    
    @staticmethod
    def check_module_permission(
        user: User, 
        module_name: str, 
        permission_key: str,
        **kwargs
    ) -> bool:
        """
        Проверить право доступа к функционалу модуля.
        
        Иерархия прав:
        1. Администратор → полный доступ
        2. Хуки модулей → контекстная проверка (например, права в организации)
        3. Ролевые группы пользователя → явно настроенные права (is_granted=True)
        4. Базовая роль "Пользователь" без групп → базовый просмотр (_view права)
        
        Args:
            user: Пользователь
            module_name: Название модуля
            permission_key: Ключ разрешения
            **kwargs: Дополнительные параметры для хуков (например, organization_id)
            
        Returns:
            True если доступ разрешен
        """
        # Администраторы имеют доступ ко всему
        if PermissionService.is_admin(user):
            return True
        
        # Вызываем зарегистрированные хуки модулей
        # Хуки могут добавлять контекстную логику (например, права в организации)
        for hook in _permission_hooks.get('check_module_permission', []):
            try:
                result = hook(user, module_name, permission_key, **kwargs)
                if result is not None:
                    return result
            except Exception:
                # Игнорируем ошибки в хуках, продолжаем проверку
                pass
        
        user_role = PermissionService.get_user_role(user)
        if not user_role:
            return False
        
        # Проверяем права в глобальных ролевых группах пользователя
        role_groups = user_role.role_groups.filter(is_active=True)
        
        # Если есть ролевые группы — проверяем явно настроенные права
        if role_groups.exists():
            for group in role_groups:
                permission = ModulePermission.objects.filter(
                    role_group=group,
                    module_name=module_name,
                    permission_key=permission_key,
                    is_granted=True
                ).first()
                
                if permission:
                    return True
            
            # Если в группах нет явного разрешения — запрещаем
            return False
        
        # Если пользователь с базовой ролью без ролевых групп:
        # Разрешаем базовый просмотр (права с суффиксом _view)
        if user_role.role.name == PermissionService.DEFAULT_ROLE_NAME:
            # Базовые права просмотра для роли "Пользователь"
            if permission_key.endswith('_view'):
                return True
        
        return False
    
    @staticmethod
    def assign_role_to_user(
        user: User, 
        role: Role, 
        role_groups: List[RoleGroup] = None,
        assigned_by: User = None
    ) -> UserRole:
        """
        Назначить роль пользователю.
        
        Args:
            user: Пользователь
            role: Роль
            role_groups: Список ролевых групп (опционально)
            assigned_by: Кто назначил роль
            
        Returns:
            Объект UserRole
        """
        # Деактивируем все существующие роли пользователя
        UserRole.objects.filter(user=user, is_active=True).update(is_active=False)
        
        # Создаем новую роль
        user_role, created = UserRole.objects.get_or_create(
            user=user,
            role=role,
            defaults={
                'is_active': True,
                'assigned_by': assigned_by
            }
        )
        
        if not created:
            user_role.is_active = True
            user_role.assigned_by = assigned_by
            user_role.save()
        
        # Назначаем ролевые группы
        if role_groups:
            user_role.role_groups.set(role_groups)
        
        PermissionService._sync_user_admin_flag(
            user,
            PermissionService._is_admin_role(role)
        )
        
        return user_role
