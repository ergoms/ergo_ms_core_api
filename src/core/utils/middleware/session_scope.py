"""
Проверка обязательных session-claim на views (не глобальный middleware).

Claim с ``required_guard=True`` декларируют модули через ``session_context.claims``.
Если провайдеров нет — проверка всегда проходит.
"""

from __future__ import annotations

from functools import wraps
from typing import Callable

from django.http import JsonResponse
from rest_framework import status
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from src.core.integrations.session_context import get_required_guard_claims

_SCOPE_REQUIRED_MESSAGE = (
    'Требуется активный контекст сессии. Выполните вход в нужный контекст.'
)


def missing_required_session_claims(request) -> list[str]:
    """Список required_guard claim, которых нет на request."""
    required = get_required_guard_claims()
    return [claim for claim in required if not getattr(request, claim, None)]


def session_scope_forbidden_response(*, drf: bool = True):
    """403 с единым текстом (DRF Response или Django JsonResponse)."""
    payload = {'error': _SCOPE_REQUIRED_MESSAGE}
    if drf:
        return Response(payload, status=status.HTTP_403_FORBIDDEN)
    return JsonResponse(payload, status=403)


class RequiresSessionScope(BasePermission):
    """
    DRF permission: на request должны быть все claim с ``required_guard``.

    Использование::

        permission_classes = [IsAuthenticated, RequiresSessionScope]
    """

    message = _SCOPE_REQUIRED_MESSAGE

    def has_permission(self, request, view) -> bool:
        return not missing_required_session_claims(request)


def session_scope_required(view_func: Callable) -> Callable:
    """
    Декоратор для FBV / ``method_decorator(..., name='dispatch')`` на CBV.

    Ожидает, что ``SessionContextMiddleware`` уже положил claims на request.
    Для ViewSet предпочтительнее ``permission_classes = [..., RequiresSessionScope]``.
    """

    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if missing_required_session_claims(request):
            from rest_framework.request import Request as DrfRequest

            if isinstance(request, DrfRequest):
                return session_scope_forbidden_response(drf=True)
            return session_scope_forbidden_response(drf=False)
        return view_func(request, *args, **kwargs)

    return wrapped
