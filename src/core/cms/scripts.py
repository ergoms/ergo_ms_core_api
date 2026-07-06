import json
import re
from dataclasses import dataclass

from src.config.settings.base import SYSTEM_DIR
from src.core.utils.auto_api.auto_config import ModuleDiscoverer

_CATCH_ALL_PATH = '/:pathMatch(.*)*'


def normalize_cms_path(path: str) -> str:
    if not path:
        return path
    if path == '/':
        return '/'
    return path[:-1] if path.endswith('/') else path


def _is_cms_route_path(path: str) -> bool:
    """Только абсолютные пути для CMSPage; без catch-all и относительных сегментов."""
    if not path or path == _CATCH_ALL_PATH or 'pathMatch' in path:
        return False
    return path.startswith('/')


def _extract_route_paths_from_js_content(content: str) -> set[str]:
    paths: set[str] = set()
    for route_path in re.findall(
        r'["\']path["\']\s*:\s*["\'](.*?)["\']',
        content,
    ):
        cleaned_path = route_path.replace('\\\\', '\\')
        normalized = normalize_cms_path(cleaned_path)
        if _is_cms_route_path(normalized):
            paths.add(normalized)
    return paths


def _extract_paths_from_client_config() -> dict[str, str]:
    """Auth и shell-маршруты из core/client/src/config/routes.js."""
    path_to_module: dict[str, str] = {}
    routes_config_path = SYSTEM_DIR / 'core' / 'client' / 'src' / 'config' / 'routes.js'

    try:
        with open(routes_config_path, 'r', encoding='utf-8') as file:
            raw = file.read()
        if raw.strip().startswith('export default'):
            raw = raw.replace('export default', '', 1).strip().rstrip(';').strip()
        routes_config = json.loads(raw)

        for section in ('coreRoutes', 'authRoutes'):
            for route in routes_config.get(section, []):
                path = route.get('path')
                if not path:
                    continue
                normalized = normalize_cms_path(path)
                if _is_cms_route_path(normalized):
                    path_to_module.setdefault(normalized, 'core')

        for route_data in routes_config.get('routes', {}).values():
            path = route_data.get('path')
            if not path:
                continue
            normalized = normalize_cms_path(path)
            if _is_cms_route_path(normalized):
                path_to_module.setdefault(normalized, 'core')
    except (OSError, json.JSONDecodeError):
        pass

    return path_to_module


def discover_client_routes_index() -> dict[str, str]:
    """Пути client-маршрутов → имя модуля (core или module)."""
    path_to_module: dict[str, str] = dict(_extract_paths_from_client_config())

    discoverer = ModuleDiscoverer()
    route_modules = discoverer.discover_client_route_modules()

    for module_key, routes_path in route_modules.items():
        try:
            _, module_name = module_key.split(':', 1)
        except ValueError:
            module_name = module_key

        try:
            with open(routes_path, 'r', encoding='utf-8') as routes_file:
                routes_content = routes_file.read()

            for normalized in _extract_route_paths_from_js_content(routes_content):
                path_to_module.setdefault(normalized, module_name)
        except OSError:
            continue

    return path_to_module


def extract_paths_from_routes_config() -> set[str]:
    """Все пути client-маршрутов для синхронизации CMSPage."""
    return set(discover_client_routes_index().keys())


@dataclass(frozen=True)
class CmsPagesSyncResult:
    """Результат синхронизации CMSPage с client-маршрутами."""

    paths: frozenset[str]
    added: frozenset[str]
    removed: frozenset[str]
    unchanged: frozenset[str]


def _existing_cms_paths_normalized() -> set[str]:
    from src.core.cms.models import CMSPage

    return {
        normalize_cms_path(path)
        for path in CMSPage.objects.values_list('path', flat=True)
    }


def _upsert_cms_page(path: str) -> bool:
    """Создать или нормализовать CMSPage. Returns True если создана новая запись."""
    from src.core.cms.models import CMSPage

    normalized = normalize_cms_path(path)
    candidates = CMSPage.objects.filter(path__in=[normalized, f'{normalized}/'])
    if candidates.exists():
        main_page = candidates.first()
        if main_page.path != normalized:
            main_page.path = normalized
            main_page.save(update_fields=['path'])
        candidates.exclude(pk=main_page.pk).delete()
        return False

    CMSPage.objects.create(path=normalized)
    return True


def sync_cms_pages(*, remove_orphans: bool = False, dry_run: bool = False) -> CmsPagesSyncResult:
    """
    Синхронизировать CMSPage с client-маршрутами.

    Args:
        remove_orphans: удалить из БД пути, которых нет в discovery (для update_routes).
        dry_run: только рассчитать diff, без записи в БД.
    """
    discovered = extract_paths_from_routes_config()
    existing = _existing_cms_paths_normalized()

    added = discovered - existing
    removed = (existing - discovered) if remove_orphans else set()
    unchanged = discovered & existing

    if not dry_run:
        for path in sorted(discovered):
            _upsert_cms_page(path)

        if removed:
            from src.core.cms.models import CMSPage

            CMSPage.objects.filter(path__in=removed).delete()

    return CmsPagesSyncResult(
        paths=frozenset(discovered),
        added=frozenset(added),
        removed=frozenset(removed),
        unchanged=frozenset(unchanged),
    )

