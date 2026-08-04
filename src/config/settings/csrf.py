"""
CSRF_TRUSTED_ORIGINS — явный список origin'ов для запросов с cookie.

Development: можно не задавать (пустой список).
Production (и любой не-development режим): обязательно CSRF_TRUSTED_ORIGINS,
иначе запуск прерывается (ImproperlyConfigured). Часто те же URL, что CORS_ALLOWED_ORIGINS.

При nginx публичный origin прокси добавляется через effective_cors_origins.
"""

from django.core.exceptions import ImproperlyConfigured

from src.config.deploy import is_development
from src.config.env import env
from src.config.nginx_runtime import effective_cors_origins


def _parse_csv_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(',') if part.strip()]


_raw = env.str('CSRF_TRUSTED_ORIGINS', default='').strip()
_parsed = _parse_csv_list(_raw)

if _parsed:
    CSRF_TRUSTED_ORIGINS = effective_cors_origins(_parsed)
elif is_development():
    CSRF_TRUSTED_ORIGINS = []
else:
    raise ImproperlyConfigured(
        'В production (и любом не-development режиме) задайте CSRF_TRUSTED_ORIGINS '
        '(часто те же URL, что CORS_ALLOWED_ORIGINS). Пустой список допустим только '
        'при ERGO_ENV=development.'
    )
