"""
JWT-токены с произвольными session-claim в payload.

Ядро не знает конкретных claim — их кладёт в токен модуль-владелец домена
через ``create_scoped_session_tokens(user, **claims)``.
Access-токен наследует claims из refresh.
"""

from __future__ import annotations

from datetime import timedelta

from rest_framework_simplejwt.tokens import RefreshToken


class ScopedSessionRefreshToken(RefreshToken):
    """RefreshToken с произвольными session-claim в payload."""

    @classmethod
    def for_user_with_claims(cls, user, **claims):
        token = cls.for_user(user)
        for key, value in claims.items():
            if value is not None:
                token[key] = value
        return token


def create_scoped_session_tokens(
    user,
    *,
    access_lifetime: timedelta | None = None,
    refresh_lifetime: timedelta | None = None,
    **claims,
) -> dict[str, str]:
    """
    Пара access/refresh с session-claim в payload.

    Returns:
        {'access': str, 'refresh': str}
    """
    refresh = ScopedSessionRefreshToken.for_user_with_claims(user, **claims)

    if refresh_lifetime:
        refresh.set_exp(lifetime=refresh_lifetime)

    access = refresh.access_token

    if access_lifetime:
        access.set_exp(lifetime=access_lifetime)

    return {
        'access': str(access),
        'refresh': str(refresh),
    }


def get_claim_from_token(token_payload, claim_key: str):
    if not token_payload:
        return None
    return token_payload.get(claim_key)
