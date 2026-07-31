"""
Шифрование чувствительных строк at rest (Fernet, ключ из Django SECRET_KEY).

Формат хранения: префикс ``enc:v1:`` + urlsafe base64 Fernet-токен.
Значения без префикса считаются plaintext (lazy dual-read / миграция).
"""

from __future__ import annotations

import base64
import hashlib
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings

logger = logging.getLogger(__name__)

_PREFIX = 'enc:v1:'


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    secret = (getattr(settings, 'SECRET_KEY', None) or '').encode('utf-8')
    if not secret:
        raise RuntimeError('SECRET_KEY пуст — нельзя инициализировать secret_box')
    # 32 url-safe base64-encoded bytes для Fernet
    digest = hashlib.sha256(secret).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def is_encrypted(value: str | None) -> bool:
    return bool(value) and str(value).startswith(_PREFIX)


def encrypt_str(plaintext: str | None) -> str:
    """Зашифровать строку. Пустая строка остаётся пустой."""
    if plaintext is None or plaintext == '':
        return ''
    if is_encrypted(plaintext):
        return plaintext
    token = _fernet().encrypt(plaintext.encode('utf-8')).decode('ascii')
    return f'{_PREFIX}{token}'


def decrypt_str(value: str | None) -> str:
    """
    Расшифровать строку. Если значение без префикса — вернуть как plaintext
    (обратная совместимость со старыми записями).
    """
    if value is None or value == '':
        return ''
    raw = str(value)
    if not is_encrypted(raw):
        return raw
    token = raw[len(_PREFIX) :].encode('ascii')
    try:
        return _fernet().decrypt(token).decode('utf-8')
    except InvalidToken:
        logger.error('secret_box: не удалось расшифровать значение (InvalidToken)')
        return ''


def encrypt_bytes(payload: bytes) -> bytes:
    if not payload:
        return b''
    return _fernet().encrypt(payload)


def decrypt_bytes(payload: bytes) -> bytes | None:
    if not payload:
        return b''
    try:
        return _fernet().decrypt(payload)
    except InvalidToken:
        logger.error('secret_box: не удалось расшифровать bytes (InvalidToken)')
        return None


def clear_fernet_cache() -> None:
    """Сброс кэша ключа (тесты)."""
    _fernet.cache_clear()
