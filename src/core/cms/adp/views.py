from rest_framework.response import Response
from rest_framework import status

from src.core.utils.base.base_views import BaseAPIView
from src.core.cms.adp.auth_cookies import clear_auth_cookies
from src.core.audit.shortcuts import audit_log


class LogoutView(BaseAPIView):
    """Очистка HttpOnly refresh-cookie (доступно без валидного access)."""

    # Идемпотентная очистка cookie: не режем throttle'ом — иначе шторм 401→logout
    # получает 429 и refresh-cookie так и не сбрасывается.
    throttle_classes = []

    def post(self, request):
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_auth_cookies(response)
        actor = request.user if getattr(request.user, 'is_authenticated', False) else None
        if actor is not None:
            audit_log('auth.logout', request=request, actor=actor)
        return response
