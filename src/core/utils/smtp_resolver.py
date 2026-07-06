"""
Разрешение SMTP-конфигурации: приоритет EmailSettings (БД), fallback — env (.env / Django settings).
"""

import logging
from dataclasses import dataclass
from typing import Literal

from django.conf import settings
from django.core.mail import get_connection

logger = logging.getLogger(__name__)

EMAIL_DISABLED_MESSAGE = 'Не удалось отправить письмо: исходящая почта не настроена'

SourceType = Literal['auto', 'env', 'db']
ConfigSource = Literal['db', 'env']


@dataclass
class SmtpConfig:
    host: str
    port: int
    username: str
    password: str
    use_tls: bool
    use_ssl: bool
    from_email: str
    source: ConfigSource


def is_email_enabled() -> bool:
    return bool(getattr(settings, 'EMAIL_ENABLED', False))


def _infer_ssl_flags(*, port: int, use_tls: bool, use_ssl: bool | None = None) -> tuple[bool, bool]:
    if use_ssl is not None:
        return use_tls, use_ssl
    if port == 465 and not use_tls:
        return False, True
    return use_tls, False


def _load_db_record():
    try:
        from src.core.settings.models import EmailSettings
        record = EmailSettings.objects.first()
        if record and record.smtp_host and record.username:
            return record
    except Exception:
        logger.debug('EmailSettings из БД недоступны, используем env-конфигурацию')
    return None


def _config_from_db(record) -> SmtpConfig:
    use_tls, use_ssl = _infer_ssl_flags(port=record.smtp_port, use_tls=record.use_tls)
    return SmtpConfig(
        host=record.smtp_host,
        port=record.smtp_port,
        username=record.username,
        password=record.password or '',
        use_tls=use_tls,
        use_ssl=use_ssl,
        from_email=record.default_from or record.username,
        source='db',
    )


def _config_from_env() -> SmtpConfig | None:
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', None)
    if not from_email:
        return None

    host = getattr(settings, 'EMAIL_HOST', '') or ''
    port = getattr(settings, 'EMAIL_PORT', None)
    username = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    password = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
    use_tls = bool(getattr(settings, 'EMAIL_USE_TLS', False))
    use_ssl = bool(getattr(settings, 'EMAIL_USE_SSL', False))

    return SmtpConfig(
        host=host,
        port=int(port) if port is not None else 0,
        username=username,
        password=password,
        use_tls=use_tls,
        use_ssl=use_ssl,
        from_email=from_email,
        source='env',
    )


def resolve_smtp_config(source: SourceType = 'auto') -> SmtpConfig | None:
    if not is_email_enabled():
        return None

    if source in ('auto', 'db'):
        record = _load_db_record()
        if record is not None:
            return _config_from_db(record)
        if source == 'db':
            return None

    return _config_from_env()


def validate_config(config: SmtpConfig | None) -> list[str]:
    if not is_email_enabled():
        return [EMAIL_DISABLED_MESSAGE]

    if config is None:
        return ['SMTP не настроен (нет EmailSettings в БД и DEFAULT_FROM_EMAIL в env)']

    missing = []
    if not config.host:
        missing.append('host (EMAIL_HOST / smtp_host)')
    if not config.port:
        missing.append('port (EMAIL_PORT / smtp_port)')
    if not config.username:
        missing.append('username (EMAIL_HOST_USER / username)')
    if not config.password:
        missing.append('password (EMAIL_HOST_PASSWORD / password)')
    if not config.from_email:
        missing.append('from_email (DEFAULT_FROM_EMAIL / default_from)')
    return missing


def build_connection(config: SmtpConfig):
    return get_connection(
        backend='django.core.mail.backends.smtp.EmailBackend',
        host=config.host,
        port=config.port,
        username=config.username,
        password=config.password,
        use_tls=config.use_tls,
        use_ssl=config.use_ssl,
    )


def resolve_connection_and_from(source: SourceType = 'auto'):
    """(connection | None, from_email | None). None-connection = дефолт Django (env)."""
    if not is_email_enabled():
        return None, None

    config = resolve_smtp_config(source=source)
    if config is None:
        return None, None

    missing = validate_config(config)
    if missing:
        return None, None

    if config.source == 'db':
        return build_connection(config), config.from_email

    return None, config.from_email


def describe_security(config: SmtpConfig) -> str:
    if config.use_ssl:
        return 'SSL'
    if config.use_tls:
        return 'TLS'
    return 'без шифрования'
