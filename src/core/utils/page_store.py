"""HTML страницы, которую разобрал парсер. Файл лежит в media, не в кэше и не в /tmp."""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qsl, urlsplit

logger = logging.getLogger(__name__)

_STEM = re.compile(r'[^0-9a-z]+')
_VALUE = re.compile(r'[^0-9a-zа-яё._-]+', re.IGNORECASE)


def store_parsed_page(namespace: str, url: str, html: str) -> str:
    """Сохранить полный текст страницы. Тот же адрес перезаписывает прежний файл."""
    if not html:
        return ''
    relative = '/'.join((*_namespace(namespace), 'pages', _page_name(url)))
    from src.core.utils.media_client import get_media_client, get_scratch_store

    with get_scratch_store().session('parsed-page') as workdir:
        temp = workdir / 'page.html'
        temp.write_text(html, encoding='utf-8', errors='replace')
        return get_media_client().commit_local(str(temp), relative)


def _namespace(namespace: str) -> tuple[str, ...]:
    parts = [part for part in namespace.replace('\\', '/').split('/') if part and part != '.']
    if not parts or any(part == '..' for part in parts):
        raise ValueError('Пустой каталог страниц парсера')
    return tuple(parts)


def _page_name(url: str) -> str:
    parts = urlsplit(url or '')
    stem = _STEM.sub('_', (parts.path.rsplit('/', 1)[-1] or 'page').casefold())
    stem = stem.removesuffix('_asp').removesuffix('_html').removesuffix('_xml').strip('_') or 'page'
    chunks = []
    for key, value in parse_qsl(parts.query, keep_blank_values=False):
        safe_key = _STEM.sub('', key.casefold())
        safe_value = _VALUE.sub('-', value.casefold()).strip('-')[:40]
        if safe_key and safe_value:
            chunks.append(f'{safe_key}-{safe_value}')
    name = stem if not chunks else f'{stem}_{"_".join(chunks)}'
    return f'{name[:180]}.html'
