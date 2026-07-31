# -*- coding: utf-8 -*-
"""Стабильные ключи каталога меню (не зависят от PK / public_id)."""

from __future__ import annotations

import re
from typing import Optional

_SLUG_RE = re.compile(r'[^a-z0-9]+')


def slugify_menu_name(name: str) -> str:
    text = (name or '').strip().lower().replace('ё', 'e')
    # транслит не обязателен: оставляем ascii + цифры, иначе hex-хвост
    ascii_part = text.encode('ascii', 'ignore').decode('ascii')
    slug = _SLUG_RE.sub('-', ascii_part).strip('-')
    if slug:
        return slug[:80]
    raw = (name or 'item').encode('utf-8')
    return 'n-' + raw.hex()[:24]


def build_item_catalog_key(
    module_source: Optional[str],
    *,
    item_type: str = 'route',
    route_name: Optional[str] = None,
    page: Optional[str] = None,
    external_url: Optional[str] = None,
    name: Optional[str] = None,
    parent_catalog_key: Optional[str] = None,
    public_id: Optional[str] = None,
) -> str:
    """
    Ключ пункта меню.

    Seed: ``{module_source}::route|{offcanvas}|{external}|{folder}::…``
    Админский пункт без module_source: ``admin::{public_id}``.
    """
    source = (module_source or '').strip()
    if not source:
        if public_id:
            return f'admin::{public_id}'
        source = 'unknown'

    if item_type == 'offcanvas' and page:
        return f'{source}::offcanvas::{page}'
    if item_type == 'external' and external_url:
        return f'{source}::external::{external_url}'
    if route_name:
        return f'{source}::route::{route_name}'

    folder_slug = slugify_menu_name(name or 'folder')
    if parent_catalog_key:
        return f'{source}::folder::{parent_catalog_key}::{folder_slug}'
    return f'{source}::folder::{folder_slug}'


def build_separator_catalog_key(
    module_source: Optional[str],
    name: str,
    *,
    public_id: Optional[str] = None,
) -> str:
    """Ключ разделителя. Админский — ``admin::separator::{public_id}``."""
    source = (module_source or '').strip()
    if not source:
        if public_id:
            return f'admin::separator::{public_id}'
        source = 'unknown'
    return f'{source}::separator::{slugify_menu_name(name)}'


def is_admin_catalog_key(catalog_key: Optional[str]) -> bool:
    return bool(catalog_key) and catalog_key.startswith('admin::')
