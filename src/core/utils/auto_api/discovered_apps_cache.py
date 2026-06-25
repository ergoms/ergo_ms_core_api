"""
Кэширование результата discovery приложений.

Снижает время запуска API, Celery worker и Beat за счёт кэширования
списка приложений в файл. Discovery выполняется только при изменении
структуры core/ или modules/. Сканирование core/ и modules/ — параллельно.
"""
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from src.config.settings.base import CORE_DIR, MODULES_DIR, VIRTUAL_ENV_DIR
from src.core.utils.auto_api.auto_config import ModuleDiscoverer

logger = logging.getLogger('utils')

CACHE_DIR = VIRTUAL_ENV_DIR / 'cache'
CACHE_FILE = CACHE_DIR / 'discovered_apps.bin'


def _max_mtime_apps_py(root: Path) -> float:
    """Max mtime всех apps.py в директории."""
    max_mtime = 0.0
    try:
        for p in root.rglob('apps.py'):
            if p.is_file():
                try:
                    max_mtime = max(max_mtime, p.stat().st_mtime)
                except OSError:
                    pass
    except OSError:
        pass
    return max_mtime


def _get_dirs_fingerprint() -> dict:
    """
    Fingerprint для проверки актуальности кэша discovered_apps.
    Учитывает mtime директорий и всех apps.py — ловит добавление/изменение приложений.
    Также включает DISABLED_MODULES — при изменении списка кэш инвалидируется.
    """
    result = {}
    for name, path in [('core', CORE_DIR), ('modules', MODULES_DIR)]:
        p = Path(path)
        if p.exists():
            try:
                dir_mtime = p.stat().st_mtime
                apps_mtime = _max_mtime_apps_py(p)
                result[f'{name}_dir'] = dir_mtime
                result[f'{name}_apps'] = max(dir_mtime, apps_mtime)
            except OSError:
                result[f'{name}_dir'] = 0
                result[f'{name}_apps'] = 0
        else:
            result[f'{name}_dir'] = 0
            result[f'{name}_apps'] = 0
    result['disabled_modules'] = os.getenv('DISABLED_MODULES', '')
    return result


def _run_discovery_fast() -> List[str]:
    """Быстрый discovery без импорта. Сканирование core/ и modules/ параллельно."""
    with ThreadPoolExecutor(max_workers=2) as ex:
        f_core = ex.submit(_collect_core_apps_fast)
        f_mod = ex.submit(_collect_module_apps_fast)
        core_apps = f_core.result()
        module_apps = f_mod.result()
    return core_apps + module_apps


def _collect_core_apps_fast() -> List[str]:
    """Собирает приложения из core/."""
    result: List[str] = []
    _recursively_find_apps_fast(str(CORE_DIR), 'src.core', result)
    return result


def _collect_module_apps_fast() -> List[str]:
    """Собирает приложения из modules/."""
    result: List[str] = []
    _find_modules_apps_fast(str(MODULES_DIR), result)
    return result


def _recursively_find_apps_fast(current_dir: str, base_module: str, installed_apps: list) -> None:
    """Рекурсивный поиск приложений по структуре (без импорта)."""
    if not os.path.isdir(current_dir):
        return
    for app_name in os.listdir(current_dir):
        app_path = os.path.join(current_dir, app_name)
        if os.path.isdir(app_path):
            module_path = f'{base_module}.{app_name}' if base_module else app_name
            if os.path.exists(os.path.join(app_path, 'apps.py')):
                installed_apps.append(module_path)
            _recursively_find_apps_fast(app_path, module_path, installed_apps)


def _find_modules_apps_fast(modules_dir: str, installed_apps: list) -> None:
    """Поиск приложений модулей по структуре (без импорта)."""
    if not os.path.isdir(modules_dir):
        return
    from src.core.utils.module_registry import get_disabled_modules
    disabled = get_disabled_modules()
    for module_name in os.listdir(modules_dir):
        if module_name in disabled:
            continue
        module_path = os.path.join(modules_dir, module_name)
        if os.path.isdir(module_path):
            api_path = os.path.join(module_path, 'api')
            if os.path.isdir(api_path):
                base_module = f'modules.{module_name}.api'
                _find_apps_in_api_fast(api_path, base_module, installed_apps)


def _find_apps_in_api_fast(current_dir: str, current_module: str, installed_apps: list) -> None:
    """Рекурсивный поиск в api/ (без импорта)."""
    if os.path.exists(os.path.join(current_dir, 'apps.py')):
        installed_apps.append(current_module)
    if not os.path.isdir(current_dir):
        return
    for app_name in os.listdir(current_dir):
        app_path = os.path.join(current_dir, app_name)
        if os.path.isdir(app_path) and app_name != '__pycache__' and not app_name.startswith('.'):
            nested_module = f'{current_module}.{app_name}'
            _find_apps_in_api_fast(app_path, nested_module, installed_apps)


def _run_discovery() -> List[str]:
    """Выполняет полное discovery с проверкой AppConfig (медленно)."""
    discoverer = ModuleDiscoverer()
    core_apps: List[str] = []
    discoverer._recursively_find_apps(str(CORE_DIR), 'src.core', core_apps)
    module_apps: List[str] = []
    discoverer._find_modules_apps(str(MODULES_DIR), module_apps)
    return core_apps + module_apps


_in_memory_cache: Optional[tuple] = None


def get_discovered_apps(use_cache: Optional[bool] = None, fast_discovery: Optional[bool] = None) -> List[str]:
    """
    Возвращает список обнаруженных приложений.

    use_cache: читать из кэша (всегда True по умолчанию)
    fast_discovery: при промахе — быстрый поиск без импорта (API_DISCOVERED_APPS_FAST_DISCOVERY)
    В пределах одного процесса результат кэшируется в памяти (fingerprint, apps).
    """
    global _in_memory_cache
    if use_cache is None:
        use_cache = True
    if fast_discovery is None:
        fast_discovery = os.getenv('API_DISCOVERED_APPS_FAST_DISCOVERY', 'true').lower() in ('1', 'true', 'yes')

    if not use_cache:
        _in_memory_cache = None
        return _run_discovery_fast() if fast_discovery else _run_discovery()

    current_fingerprint = _get_dirs_fingerprint()
    if _in_memory_cache is not None:
        from src.core.utils.cache_fingerprint import fingerprint_equal
        if fingerprint_equal(_in_memory_cache[0], current_fingerprint):
            return _in_memory_cache[1]

    from src.core.utils.cache_fingerprint import fingerprint_equal
    from src.core.utils.cache_io import read_bin_cache

    data = read_bin_cache(CACHE_FILE)
    if data is not None:
        cached_fingerprint = data.get('fingerprint', {})
        if fingerprint_equal(cached_fingerprint, current_fingerprint):
            apps = data.get('apps')
            if apps is not None:
                _in_memory_cache = (current_fingerprint, apps)
                logger.debug('Discovered apps: загружено из кэша')
                return apps

    apps = _run_discovery_fast() if fast_discovery else _run_discovery()
    from src.core.utils.cache_io import write_bin_cache

    if write_bin_cache(CACHE_FILE, {'fingerprint': current_fingerprint, 'apps': apps}):
        logger.info('Discovered apps: сохранено в кэш (%d приложений)', len(apps))

    _in_memory_cache = (current_fingerprint, apps)
    return apps
