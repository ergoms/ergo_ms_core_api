import logging

from channels.db import database_sync_to_async
from django.contrib.auth import get_user_model

logger = logging.getLogger('core.cms.adp')

User = get_user_model()


@database_sync_to_async
def user_from_jwt_token(token: str):
    try:
        from rest_framework_simplejwt.tokens import UntypedToken
        from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
    except Exception:
        logger.exception('rest_framework_simplejwt не установлен')
        return None

    try:
        validated = UntypedToken(token)
    except (InvalidToken, TokenError):
        return None
    except Exception:
        logger.exception('Не удалось разобрать JWT для WebSocket')
        return None

    user_id = validated.get('user_id')
    if not user_id:
        return None
    try:
        return User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return None
