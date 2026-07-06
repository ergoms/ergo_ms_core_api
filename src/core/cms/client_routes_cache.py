"""
Кэш индекса client-маршрутов (path → module).

Снижает нагрузку на GetCMSPages и sync_cms_pages: discovery выполняется
только при изменении routes.js в core/ или modules/.
"""

import logging
from pathlib import Path

from src.config.settings.base import CORE_DIR, MODULES_DIR, SYSTEM_DIR, VIRTUAL_ENV_DIR
from src.core.cms.scripts import discover_client_routes_index
from src.core.utils.auto_api.auto_config import ModuleDiscoverer
from src.core.utils.cache_io import read_bin_cache, write_bin_cache

logger = logging.getLogger('utils')

CACHE_DIR = VIRTUAL_ENV_DIR / 'cache'
CACHE_FILE = CACHE_DIR / 'client_routes_index.bin'


def _max_mtime_routes_js(root: Path) -> float:
    max_mtime = 0.0
    try:
        for pattern in ('routes.js',):
            for path in root.rglob(pattern):
                if path.is_file() and 'node_modules' not in path.parts:
                    try:
                        max_mtime = max(max_mtime, path.stat().st_mtime)
                    except OSError:
                        pass
    except OSError:
        pass
    return max_mtime


def _get_fingerprint() -> dict:
    result = {}
    core_config = SYSTEM_DIR / 'core' / 'client' / 'src' / 'config' / 'routes.js'
    if core_config.exists():
        try:
            result['core_routes_js'] = core_config.stat().st_mtime
        except OSError:
            result['core_routes_js'] = 0
    else:
        result['core_routes_js'] = 0

    for name, path in (('core', CORE_DIR), ('modules', MODULES_DIR)):
        p = Path(path)
        if p.exists():
            try:
                result[f'{name}_dir'] = p.stat().st_mtime
                result[f'{name}_routes'] = _max_mtime_routes_js(p)
            except OSError:
                result[f'{name}_dir'] = 0
                result[f'{name}_routes'] = 0
        else:
            result[f'{name}_dir'] = 0
            result[f'{name}_routes'] = 0

    discoverer = ModuleDiscoverer()
    result['route_modules_count'] = len(discoverer.discover_client_route_modules())
    return result


def _is_cache_valid(cached: dict) -> bool:
    if not isinstance(cached, dict):
        return False
    if cached.get('fingerprint') != _get_fingerprint():
        return False
    data = cached.get('data')
    return isinstance(data, dict)


def get_client_routes_index(*, use_cache: bool = True) -> dict[str, str]:
    if use_cache:
        cached = read_bin_cache(CACHE_FILE)
        if _is_cache_valid(cached):
            return dict(cached['data'])

    data = discover_client_routes_index()
    payload = {
        'fingerprint': _get_fingerprint(),
        'data': data,
    }
    if use_cache:
        write_bin_cache(CACHE_FILE, payload)
        logger.debug('Кэш client routes index обновлён (%s путей)', len(data))
    return data


def invalidate_client_routes_index_cache() -> None:
    """Удаляет файловый кэш индекса client-маршрутов."""
    try:
        CACHE_FILE.unlink(missing_ok=True)
    except OSError:
        logger.warning('Не удалось удалить %s', CACHE_FILE, exc_info=True)
