"""Скачивание подписанного пакета справки с media_api владельца.

Через туннель до чужого порта media_api отдельное соединение иногда не
устанавливается и висит до таймаута. Один такой обрыв помечает весь пакет
недоступным, поэтому запрос повторяется новым соединением.
"""

from __future__ import annotations

import logging

logger = logging.getLogger('utils.knowledge_pack')

# Файл справки маленький. Зависшее соединение обрываем раньше и открываем новое,
# а не ждём одни и те же 30 секунд до отказа всего пакета.
PACK_DOWNLOAD_TIMEOUT_SECONDS = 10
PACK_DOWNLOAD_ATTEMPTS = 3


def _nginx_front_for_accel(url: str) -> str | None:
    """Порт media_api с X-Accel-Redirect отдаёт пустое тело. Файл читает nginx того же хоста."""
    from urllib.parse import urlsplit, urlunsplit

    parsed = urlsplit(url)
    if parsed.scheme not in ('http', 'https') or not parsed.hostname:
        return None
    if parsed.port in (None, 80, 443):
        return None
    rewritten = urlunsplit((parsed.scheme, parsed.hostname, parsed.path, parsed.query, ''))
    if rewritten == url:
        return None
    return rewritten


def _transient_download_error(exc: BaseException) -> bool:
    from urllib.error import HTTPError, URLError

    if isinstance(exc, HTTPError):
        return 500 <= int(exc.code) <= 599
    return isinstance(exc, (URLError, TimeoutError))


def _read_http_response(
    opener,
    url: str,
    extra_headers: dict[str, str] | None = None,
) -> tuple[bytes, dict[str, str]]:
    from urllib.request import Request

    request = Request(url, headers=dict(extra_headers or {}))
    with opener.open(  # noqa: S310 — схема уже ограничена
        request,
        timeout=PACK_DOWNLOAD_TIMEOUT_SECONDS,
    ) as response:
        body = response.read()
        raw_headers = getattr(response, 'headers', None)
        headers: dict[str, str] = {}
        if raw_headers is not None:
            try:
                headers = {str(key).lower(): str(value) for key, value in raw_headers.items()}
            except (TypeError, ValueError):
                headers = {}
        return body, headers


def _open_knowledge_url(opener, url: str, extra_headers: dict[str, str] | None = None):
    try:
        return _read_http_response(opener, url, extra_headers)
    except Exception as exc:
        logger.debug(
            'Пакет справки не прочитан с %s: %s',
            (extra_headers or {}).get('Host') or '',
            _pack_download_error_text(url, exc),
        )
        return b'', {}


def _read_media_with_retry(url: str) -> tuple[bytes, dict[str, str]]:
    from src.core.utils.http_proxy import urllib_opener

    attempt = 1
    while True:
        try:
            return _read_http_response(urllib_opener(), url)
        except Exception as exc:
            if attempt >= PACK_DOWNLOAD_ATTEMPTS or not _transient_download_error(exc):
                raise
            attempt += 1
            logger.debug(
                'Повтор скачивания пакета справки, попытка %s: %s',
                attempt,
                _pack_download_error_text(url, exc),
            )


def _http_get_knowledge_bytes(url: str) -> bytes:
    from urllib.parse import urlparse

    from src.core.utils.http_proxy import urllib_opener

    parsed = urlparse(url)
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('Недопустимый URL пакета справки')
    if '/serve/knowledge/' not in (parsed.path or ''):
        raise ValueError('URL не указывает на пакет справки')
    body, headers = _read_media_with_retry(url)
    if body or not headers.get('x-accel-redirect'):
        return body
    nginx_url = _nginx_front_for_accel(url)
    if not nginx_url:
        return body
    hostname = urlparse(nginx_url).hostname or ''
    logger.info(
        'Пакет справки отдан через X-Accel-Redirect, повтор через nginx %s',
        hostname,
    )
    # В шаблоне nginx server_name всегда включает localhost. Чужой Host (IP
    # пира) такой сервер закрывает без ответа, поэтому localhost пробуем первым.
    opener = urllib_opener()
    body, _headers = _open_knowledge_url(opener, nginx_url, {'Host': 'localhost'})
    if body:
        return body
    body, _headers = _open_knowledge_url(opener, nginx_url)
    if not body:
        logger.warning('nginx %s не отдал файл пакета справки', hostname)
    return body


def _pack_download_error_text(url: str, exc: BaseException) -> str:
    from urllib.error import HTTPError, URLError
    from urllib.parse import urlparse

    host = urlparse(url).netloc or '?'
    if isinstance(exc, HTTPError):
        return f'HTTP {exc.code} с {host}'
    if isinstance(exc, URLError):
        return f'{exc.reason} ({host})'
    return f'{exc} ({host})'


def _read_pack_file(storage_path: str, *, signer: str) -> bytes | None:
    from src.core.integrations import bridge
    from src.core.utils.knowledge_pack import knowledge_sign_read_op
    from src.core.utils.media_client import get_media_client

    client = get_media_client()
    try:
        if client.exists(storage_path):
            return client.read_bytes(storage_path)
    except Exception:
        logger.debug('Локальное чтение %s не удалось', storage_path, exc_info=True)
    signed = bridge.call(
        knowledge_sign_read_op(signer),
        path=storage_path,
        default=None,
    )
    if not isinstance(signed, dict) or not signed.get('url'):
        logger.warning('Нет подписи для пакета %s (signer=%s)', storage_path, signer)
        return None
    url = str(signed['url'])
    try:
        return _http_get_knowledge_bytes(url)
    except Exception as exc:
        logger.warning('Не удалось скачать %s: %s', storage_path, _pack_download_error_text(url, exc))
        return None
