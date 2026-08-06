"""Object-level permission hooks (security audit С8, phase 1).

Точки расширения для ViewSet/APIView и permission-классов DRF.
По умолчанию доступ разрешён — существующие представления не ломаются
до явной миграции на object-scope.
"""

from __future__ import annotations

from typing import Any


class ObjectPermissionMixin:
    """
    Миксин / база для object-scoped проверок.

    Подклассы MUST переопределить ``check_object_permission`` и/или
    фильтровать queryset через ``filter_queryset_for_user``.
    Дефолт — True (phase 1 stub), чтобы не менять поведение до миграции.
    """

    def check_object_permission(self, request: Any, obj: Any) -> bool:
        """Override for object scope. Default allows access."""
        return True

    def has_object_permission(self, request: Any, view: Any, obj: Any) -> bool:
        """
        DRF BasePermission-compatible entry.

        Delegates to ``check_object_permission(request, obj)``.
        When used as a ViewSet mixin, ``view`` is typically ``self``.
        """
        return self.check_object_permission(request, obj)


def filter_queryset_for_user(queryset: Any, user: Any) -> Any:
    """
    Extension point: restrict queryset to objects the user may see.

    Default returns queryset unchanged. Call from ``get_queryset`` after
    adopting ObjectPermissionMixin / object-scope rules.
    """
    return queryset
