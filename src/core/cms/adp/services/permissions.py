"""
Сервис для проверки прав доступа пользователей к ресурсам системы.
"""
import re
from typing import List, Dict, Optional
from django.contrib.auth.models import User
from src.core.cms.adp.middleware.permission_request_cache import get_request_permission_cache
from src.core.cms.adp.models import Role, RoleGroup, Policy, UserRole, ModulePermission
from src.core.integrations import bridge


PERMISSION_CHECK_EVENT = 'adp.permission_check'


class RoleAssignmentError(Exception):
    """Недопустимое изменение роли пользователя."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class PermissionService:
    """
    Сервис для работы с правами доступа пользователей.
    """
    DEFAULT_ROLE_NAME = 'Пользователь'
    DEFAULT_ROLE_DESCRIPTION = 'Роль по умолчанию для всех пользователей'
    ADMIN_ROLE_NAME = 'Администратор'
    ADMIN_ROLE_DESCRIPTION = 'Системная роль с полным доступом'
    
    @staticmethod
    def get_user_role(user: User) -> Optional[UserRole]:
        """Получить активную роль пользователя (без побочных save на read-path)."""
        if not user or not getattr(user, 'pk', None):
            return None

        cache = get_request_permission_cache()
        cache_key = f'user_role:{user.pk}'
        if cache_key in cache:
            return cache[cache_key]

        user_role = (
            UserRole.objects
            .select_related('role')
            .prefetch_related('role_groups')
            .filter(user=user, is_active=True)
            .first()
        )

        if user_role:
            cache[cache_key] = user_role
            return user_role

        cache[cache_key] = None
        return None

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
    def _sync_django_admin_flags(user: User, should_be_admin: bool):
        """
        Синхронизирует is_staff и is_superuser с ADP-ролью администратора (единая сущность).
        """
        if not getattr(user, 'pk', None):
            return

        update_fields = []
        if getattr(user, 'is_staff', False) != should_be_admin:
            user.is_staff = should_be_admin
            update_fields.append('is_staff')
        if getattr(user, 'is_superuser', False) != should_be_admin:
            user.is_superuser = should_be_admin
            update_fields.append('is_superuser')
        if update_fields:
            user.save(update_fields=update_fields)

    @staticmethod
    def count_global_admins() -> int:
        from django.db.models import Q

        admin_role = PermissionService._get_or_create_admin_role()
        return (
            User.objects.filter(
                Q(is_superuser=True)
                | Q(user_roles__role=admin_role, user_roles__is_active=True)
            )
            .distinct()
            .count()
        )

    @staticmethod
    def validate_role_change(
        user: User,
        role: Role,
        assigned_by: User = None,
    ) -> Optional[str]:
        was_admin = PermissionService._is_global_admin(user)
        will_be_admin = PermissionService._is_admin_role(role)
        if was_admin and not will_be_admin:
            if assigned_by and assigned_by.pk == user.pk:
                return 'Нельзя снять с себя роль администратора.'
            if PermissionService.count_global_admins() <= 1:
                return 'Нельзя снять роль у последнего администратора системы.'
        return None

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
        PermissionService._sync_django_admin_flags(user, False)
        return user_role
    
    @staticmethod
    def _get_active_user_role(user: User) -> Optional[UserRole]:
        """Активная роль без побочных эффектов (не назначает роль по умолчанию)."""
        if not user or not getattr(user, 'pk', None):
            return None
        return UserRole.objects.select_related('role').filter(
            user=user,
            is_active=True,
        ).first()

    @staticmethod
    def _is_global_admin(user: User) -> bool:
        """
        Глобальный администратор: is_superuser и активная ADP-роль admin синхронизированы
        (_sync_django_admin_flags). Проверяем оба источника для устойчивости.
        """
        if not user or not getattr(user, 'is_authenticated', False):
            return False

        cache = get_request_permission_cache()
        cache_key = f'is_global_admin:{user.pk}'
        if cache_key in cache:
            return cache[cache_key]

        if getattr(user, 'is_superuser', False):
            cache[cache_key] = True
            return True
        user_role = PermissionService._get_active_user_role(user)
        result = bool(
            user_role
            and user_role.is_active
            and PermissionService._is_admin_role(user_role.role)
        )
        cache[cache_key] = result
        return result

    @staticmethod
    def is_admin(user: User) -> bool:
        """Проверить, является ли пользователь глобальным администратором."""
        return PermissionService._is_global_admin(user)

    @staticmethod
    def can_manage_users_as_global_admin(user: User) -> bool:
        """Глобальный администратор (эквивалент is_admin)."""
        return PermissionService._is_global_admin(user)

    @staticmethod
    def can_access_admin_panel(user: User) -> bool:
        """Доступ к панели администратора — эквивалент глобального админа."""
        return PermissionService.can_manage_users_as_global_admin(user)

    @staticmethod
    def resolve_display_role(
        user: User,
        user_role: Optional[UserRole] = None,
        *,
        admin_role: Optional[Role] = None,
    ) -> Optional[Role]:
        """Эффективная роль для отображения в админ-панели."""
        if PermissionService._is_global_admin(user):
            if user_role and user_role.role:
                return user_role.role
            return admin_role or PermissionService._get_or_create_admin_role()

        if user_role and user_role.role:
            return user_role.role

        return None
    
    @staticmethod
    def _get_url_policies_for_user(user: User, user_role: UserRole) -> list:
        cache = get_request_permission_cache()
        cache_key = f'url_policies:{user.pk}'
        if cache_key in cache:
            return cache[cache_key]

        policies = list(
            Policy.objects.filter(
                role=user_role.role,
                policy_type='url',
                is_active=True,
            )
        )
        group_ids = [
            group.id
            for group in user_role.role_groups.all()
            if group.is_active
        ]
        if group_ids:
            policies.extend(
                Policy.objects.filter(
                    role_group_id__in=group_ids,
                    policy_type='url',
                    is_active=True,
                )
            )
        cache[cache_key] = policies
        return policies

    @staticmethod
    def _get_granted_module_permission_keys(user: User) -> set[tuple[str, str]]:
        cache = get_request_permission_cache()
        cache_key = f'module_perm_keys:{user.pk}'
        if cache_key in cache:
            return cache[cache_key]

        user_role = PermissionService.get_user_role(user)
        if not user_role:
            cache[cache_key] = set()
            return cache[cache_key]

        group_ids = [
            group.id
            for group in user_role.role_groups.all()
            if group.is_active
        ]
        if not group_ids:
            cache[cache_key] = set()
            return cache[cache_key]

        rows = ModulePermission.objects.filter(
            role_group_id__in=group_ids,
            is_granted=True,
        ).values_list('module_name', 'permission_key')
        result = {(module_name, permission_key) for module_name, permission_key in rows}
        cache[cache_key] = result
        return result

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
            return False

        policies = PermissionService._get_url_policies_for_user(user, user_role)

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
            is_global_admin = PermissionService.is_admin(user)
            return {
                'user_id': user.id,
                'username': user.username,
                'role': None,
                'role_groups': [],
                'allowed_urls': [],
                'denied_urls': [],
                'module_permissions': [],
                'is_global_admin': is_global_admin,
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
            'module_permissions': module_permissions,
            'is_global_admin': PermissionService.is_admin(user),
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

        # Вызываем подписчиков события 'adp.permission_check'.
        # Подписчики (например, organizations) добавляют контекстную логику.
        # Первый non-None результат побеждает.
        contextual = bridge.emit_first(
            PERMISSION_CHECK_EVENT,
            user=user,
            module_name=module_name,
            permission_key=permission_key,
            kwargs=kwargs,
        )
        if contextual is not None:
            return contextual

        user_role = PermissionService.get_user_role(user)
        if not user_role:
            return False

        role_groups = [group for group in user_role.role_groups.all() if group.is_active]

        if role_groups:
            granted = PermissionService._get_granted_module_permission_keys(user)
            return (module_name, permission_key) in granted

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
        validation_error = PermissionService.validate_role_change(user, role, assigned_by)
        if validation_error:
            raise RoleAssignmentError(validation_error)

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
        
        PermissionService._sync_django_admin_flags(
            user,
            PermissionService._is_admin_role(role),
        )

        from src.core.cms.adp.services.permissions_snapshot_cache import (
            invalidate_user_permissions_snapshot,
        )

        invalidate_user_permissions_snapshot(user.pk)

        return user_role
