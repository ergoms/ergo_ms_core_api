"""Локальный lookup геолокации IP по DB-IP City Lite (MMDB)."""

from __future__ import annotations

import ipaddress
import logging
from functools import lru_cache

from django.conf import settings

from src.core.cms.adp.user_agent_utils import format_device_location

logger = logging.getLogger(__name__)

_UNKNOWN = ('Неизвестно', 'Неизвестно')
_reader = None


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_reserved
        or addr.is_multicast
    )


def _get_reader():
    global _reader
    if not getattr(settings, 'GEOIP_ENABLED', False):
        return None
    if _reader is not None:
        return _reader
    try:
        import geoip2.database
    except ImportError:
        logger.warning('Пакет geoip2 не установлен; геолокация IP отключена')
        return None

    db_path = settings.GEOIP_PATH / settings.GEOIP_CITY_DB
    if not db_path.is_file():
        logger.warning('GeoIP database not found: %s', db_path)
        return None

    try:
        locales = list(getattr(settings, 'GEOIP_LOCALES', ['ru']) or ['ru'])
        if 'en' not in locales:
            locales.append('en')
        _reader = geoip2.database.Reader(str(db_path), locales=locales)
    except Exception:
        logger.exception('Failed to open GeoIP database: %s', db_path)
        return None
    return _reader


def reset_geoip_reader_cache() -> None:
    """Закрывает reader и сбрасывает кэш lookup (после обновления .mmdb)."""
    global _reader
    if _reader is not None:
        try:
            _reader.close()
        except Exception:
            logger.exception('Failed to close GeoIP reader')
        _reader = None
    resolve_ip_location.cache_clear()


def _extract_city_country(response) -> tuple[str, str]:
    city = (response.city.name or '').strip() or 'Неизвестно'
    country = (response.country.name or '').strip() or 'Неизвестно'
    return city, country


@lru_cache(maxsize=4096)
def resolve_ip_location(ip: str) -> tuple[str, str]:
    """Возвращает (city, country) для UI; при ошибке — ('Неизвестно', 'Неизвестно')."""
    normalized = (ip or '').strip()
    if not normalized or not _is_public_ip(normalized):
        return _UNKNOWN

    reader = _get_reader()
    if reader is None:
        return _UNKNOWN

    try:
        return _extract_city_country(reader.city(normalized))
    except Exception:
        logger.debug('GeoIP lookup failed for address', exc_info=True)
        return _UNKNOWN


def format_ip_location(ip: str | None) -> str:
    city, country = resolve_ip_location(ip or '')
    return format_device_location(city, country)
