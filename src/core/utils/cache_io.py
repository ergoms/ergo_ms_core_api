"""
Утилиты для записи/чтения кэша.
Использует JSON + HMAC-подпись вместо pickle для предотвращения
insecure deserialization при компрометации файловой системы.
"""

import hashlib
import hmac
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger('utils.cache')

_SIGNATURE_SEPARATOR = b'\n---SIGNATURE---\n'
_PICKLE_MAGIC = b'\x80'
_UNSET = object()
_cached_signing_key: Any = _UNSET


def _read_secret_key_from_dotenv() -> Optional[str]:
    """Читает API_SECRET_KEY из корневого .env без django.setup."""
    for parent in Path(__file__).resolve().parents:
        env_file = parent / '.env'
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding='utf-8').splitlines():
                    line = line.strip()
                    if not line or line.startswith('#') or '=' not in line:
                        continue
                    key, _, value = line.partition('=')
                    if key.strip() == 'API_SECRET_KEY':
                        return value.strip().strip('"').strip("'")
            except OSError:
                pass
        if (parent / 'modules').is_dir() and (parent / 'core').is_dir():
            break
    return None


def _get_signing_key() -> Optional[bytes]:
    """
    Ключ подписи из os.environ / .env (без django.conf — кэш читается до django.setup).

    Без ключа чтение/запись кэша отключается (None) — нет небезопасного fallback.
    """
    global _cached_signing_key
    if _cached_signing_key is not _UNSET:
        return _cached_signing_key
    key = (
        os.environ.get('API_SECRET_KEY')
        or os.environ.get('CACHE_SIGNING_KEY')
        or _read_secret_key_from_dotenv()
    )
    if not key or key in ('secret-key', 'django-insecure', 'ergo-cache-signing-key'):
        logger.warning(
            'Ключ подписи кэша не задан или небезопасен — файловый кэш отключён'
        )
        _cached_signing_key = None
        return None
    _cached_signing_key = key.encode()
    return _cached_signing_key


def write_bin_cache(path: Path, data: Any) -> bool:
    """Записывает данные в JSON-кэш с HMAC-подписью. Возвращает True при успехе."""
    signing_key = _get_signing_key()
    if signing_key is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')
        signature = hmac.HMAC(signing_key, payload, hashlib.sha256).digest()
        with open(path, 'wb') as f:
            f.write(payload)
            f.write(_SIGNATURE_SEPARATOR)
            f.write(signature)
        return True
    except (OSError, TypeError, ValueError) as e:
        logger.warning('Не удалось записать кэш %s: %s', path.name, e)
        return False


def read_bin_cache(path: Path) -> Optional[Any]:
    """Читает данные из JSON-кэша с проверкой HMAC. Возвращает None при ошибке."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    signing_key = _get_signing_key()
    if signing_key is None:
        return None
    try:
        raw = path.read_bytes()
        if raw.startswith(_PICKLE_MAGIC):
            # Legacy pickle больше не читаем (insecure deserialization).
            logger.warning(
                'Устаревший pickle-кэш %s проигнорирован — будет пересоздан',
                path.name,
            )
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        if _SIGNATURE_SEPARATOR in raw:
            payload, signature = raw.rsplit(_SIGNATURE_SEPARATOR, 1)
            expected = hmac.HMAC(signing_key, payload, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                logger.warning('Подпись кэша %s невалидна — будет пересоздан', path.name)
                return None
            return json.loads(payload)
        # Подпись обязательна — unsigned JSON не принимаем
        logger.warning('Кэш %s без подписи — будет пересоздан', path.name)
        return None
    except (json.JSONDecodeError, OSError, ValueError):
        return None
