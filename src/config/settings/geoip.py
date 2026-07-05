"""Настройки локальной геолокации IP (DB-IP City Lite, MMDB)."""

from datetime import date

from src.config.env import env
from src.config.settings.base import RESOURCES_DIR

GEOIP_ENABLED = env.bool('GEOIP_ENABLED', default=True)
GEOIP_PATH = RESOURCES_DIR / 'geoip'
GEOIP_CITY_DB = 'dbip-city-lite.mmdb'

# Явный URL в .env — предпочтительно; иначе авто по текущему месяцу (см. resolve_geoip_download_url).
GEOIP_DOWNLOAD_URL = env.str('GEOIP_DOWNLOAD_URL', default='').strip()

GEOIP_DOWNLOAD_URL_TEMPLATE = (
    'https://download.db-ip.com/free/dbip-city-lite-{month}.mmdb.gz'
)
GEOIP_DOWNLOAD_FALLBACK_MONTHS = 3

GEOIP_LOCALES = ['ru']


def resolve_geoip_download_url() -> str:
    if GEOIP_DOWNLOAD_URL:
        return GEOIP_DOWNLOAD_URL
    month = date.today().strftime('%Y-%m')
    return GEOIP_DOWNLOAD_URL_TEMPLATE.format(month=month)


def iter_geoip_download_url_candidates(primary_url: str | None = None) -> list[str]:
    """Primary URL + fallback на предыдущие месяцы (если primary — шаблон db-ip)."""
    seen: set[str] = set()
    urls: list[str] = []

    def add(url: str) -> None:
        normalized = (url or '').strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            urls.append(normalized)

    add(primary_url or resolve_geoip_download_url())

    today = date.today()
    for month_offset in range(GEOIP_DOWNLOAD_FALLBACK_MONTHS):
        month = today.month - month_offset
        year = today.year
        while month <= 0:
            month += 12
            year -= 1
        add(GEOIP_DOWNLOAD_URL_TEMPLATE.format(month=f'{year:04d}-{month:02d}'))

    return urls
