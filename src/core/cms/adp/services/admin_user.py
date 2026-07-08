"""Создание пользователей администратором (в обход публичной регистрации)."""

from __future__ import annotations

from typing import Optional

from django.contrib.auth import get_user_model

User = get_user_model()
from django.db import transaction

from src.core.cms.adp.models import Role, RoleGroup, UserProfile
from src.core.cms.adp.password_policy import validate_password_value
from src.core.cms.adp.services.permissions import PermissionService, RoleAssignmentError
from src.core.cms.adp.services.registration import RegistrationService
from src.core.utils.methods import (
    generate_secure_random_password,
    send_admin_password_reset_notification,
)


class AdminUserCreateError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@transaction.atomic
def create_admin_user(
    *,
    username: str,
    created_by: User,
    password: str = '',
    first_name: str = '',
    last_name: str = '',
    middle_name: str = '',
    email: str = '',
    role_id: Optional[int] = None,
    role_group_ids: Optional[list] = None,
    send_password_notification: bool = True,
) -> tuple[User, dict]:
    normalized_username = (username or '').strip()
    if not normalized_username:
        raise AdminUserCreateError('Логин обязателен.')

    if User.objects.filter(username__iexact=normalized_username).exists():
        raise AdminUserCreateError('Данный логин уже занят, попробуйте другой.')

    normalized_email = (email or '').strip().lower()
    if normalized_email:
        email_error = RegistrationService.validate_email_uniqueness(normalized_email)
        if email_error:
            raise AdminUserCreateError(email_error)

    manual_password = (password or '').strip()
    password_mode = 'manual' if manual_password else 'system'
    if password_mode == 'manual':
        try:
            validate_password_value(manual_password)
        except Exception as exc:
            messages = getattr(exc, 'messages', None) or [str(exc)]
            raise AdminUserCreateError(messages[0]) from exc
        user_password = manual_password
    else:
        user_password = generate_secure_random_password()

    user = User.objects.create_user(
        username=normalized_username,
        first_name=(first_name or '').strip(),
        last_name=(last_name or '').strip(),
        middle_name=(middle_name or '').strip(),
        email=normalized_email,
        password=user_password,
    )
    del user_password

    profile, _ = UserProfile.objects.get_or_create(user=user)

    role_groups = []
    if role_id:
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist as exc:
            raise AdminUserCreateError('Роль не найдена.') from exc

        if role_group_ids:
            role_groups = list(RoleGroup.objects.filter(id__in=role_group_ids))

        try:
            PermissionService.assign_role_to_user(
                user=user,
                role=role,
                role_groups=role_groups,
                assigned_by=created_by,
            )
        except RoleAssignmentError as exc:
            raise AdminUserCreateError(exc.message) from exc

    email_sent = False
    email_error = None
    if password_mode == 'system' and send_password_notification:
        if normalized_email:
            email_sent, email_error = send_admin_password_reset_notification(normalized_email)
        else:
            email_error = 'У пользователя не указан email — уведомление не отправлено.'

    meta = {
        'password_mode': password_mode,
        'email_sent': email_sent,
        'email_warning': email_error if password_mode == 'system' and email_error else None,
    }
    return user, meta
