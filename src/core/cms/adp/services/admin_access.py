"""Общие проверки доступа для admin API ADP."""

from rest_framework import status
from rest_framework.response import Response

from src.core.cms.adp.services.permissions import PermissionService


def require_global_admin_response(request):
    """403 Response, если пользователь не глобальный администратор; иначе None."""
    if PermissionService.can_manage_users_as_global_admin(request.user):
        return None
    return Response({'detail': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)
