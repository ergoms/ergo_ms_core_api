"""
Внутренние эндпоинты для инфраструктуры (nginx auth_request и т.п.).
"""

from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from src.core.cms.adp.auth_cookies import get_refresh_token_from_request
from src.core.cms.adp.authentication import DeviceBoundJWTAuthentication
from src.core.cms.adp.services.permissions import PermissionService

User = get_user_model()


def _user_from_access_header(request):
    auth_header = request.META.get('HTTP_AUTHORIZATION', '')
    if not auth_header.startswith('Bearer '):
        return None
    raw_token = auth_header[7:].strip()
    if not raw_token:
        return None
    authenticator = DeviceBoundJWTAuthentication()
    try:
        validated = authenticator.get_validated_token(raw_token)
        return authenticator.get_user(validated)
    except (InvalidToken, TokenError):
        return None
    except Exception:
        return None


def _user_from_refresh_cookie(request):
    refresh_value = get_refresh_token_from_request(request)
    if not refresh_value:
        return None
    try:
        token = RefreshToken(refresh_value)
        user_id = token.get('user_id')
        if user_id is None:
            return None
        return User.objects.filter(pk=user_id, is_active=True).first()
    except (InvalidToken, TokenError):
        return None
    except Exception:
        return None


def resolve_jupyter_gate_user(request):
    """Пользователь для nginx auth_request: access JWT или refresh-cookie."""
    user = _user_from_access_header(request)
    if user is not None:
        return user
    return _user_from_refresh_cookie(request)


class JupyterAccessView(APIView):
    """
    Проверка доступа к Jupyter за nginx (auth_request).

    200 — глобальный администратор; 401 — не аутентифицирован; 403 — нет прав.
    """

    authentication_classes = []
    permission_classes = []
    throttle_classes = []

    def get(self, request):
        return self._check(request)

    def head(self, request):
        return self._check(request)

    def _check(self, request):
        user = resolve_jupyter_gate_user(request)
        if user is None:
            return Response(status=401)
        if not PermissionService.is_admin(user):
            return Response(status=403)
        return Response(status=200)
