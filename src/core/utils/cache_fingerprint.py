"""
Унифицированная логика fingerprint и валидации кэшей.

- MTIME_TOLERANCE — снижает ложные инвалидации из-за неточностей mtime (Windows, NFS)
- get_celery_config_fingerprint() — единый fingerprint для celery кэшей
- mtime_equal() — сравнение mtime с допуском
"""
from pathlib import Path
from typing import Dict

MTIME_TOLERANCE = 2.0


def mtime_equal(stored: float, current: float) -> bool:
    """Сравнивает mtime с допуском, снижает ложные инвалидации."""
    return abs(stored - current) <= MTIME_TOLERANCE


def mtime_valid(stored: float, current: float) -> bool:
    """Кэш валиден, если stored >= current с учётом допуска (ничего не изменилось)."""
    if stored >= current:
        return True
    return mtime_equal(stored, current)


def get_celery_config_fingerprint(
    project_root: Path,
    modules_dir: Path,
) -> Dict[str, float]:
    """Fingerprint для celery routes/queues/beat на основе mtime конфигов."""
    result: Dict[str, float] = {}
    if modules_dir.exists():
        result['modules'] = modules_dir.stat().st_mtime
        for module_dir in sorted(modules_dir.iterdir()):
            if not module_dir.is_dir():
                continue
            module_env = module_dir / '.env'
            if module_env.exists():
                key = str(module_env.relative_to(project_root))
                result[key] = module_env.stat().st_mtime
            for cfg_name in ('celery_config.py', 'celery_beat_config.py'):
                cfg = module_dir / cfg_name
                if cfg.exists():
                    key = str(cfg.relative_to(project_root))
                    result[key] = cfg.stat().st_mtime
            api_cfg = module_dir / 'api' / 'celery_config.py'
            if api_cfg.exists():
                key = str(api_cfg.relative_to(project_root))
                result[key] = api_cfg.stat().st_mtime
    core_path = project_root / 'core'
    if core_path.exists():
        result['core'] = core_path.stat().st_mtime
    return result


def get_modules_config_max_mtime(modules_dir: Path) -> float:
    """Max mtime по celery_config.py / celery_beat_config.py модулей."""
    max_mtime = 0.0
    if not modules_dir.exists():
        return max_mtime
    max_mtime = modules_dir.stat().st_mtime
    for module_dir in modules_dir.iterdir():
        if not module_dir.is_dir():
            continue
        for cfg_name in ('celery_config.py', 'celery_beat_config.py'):
            cfg = module_dir / cfg_name
            if cfg.exists():
                max_mtime = max(max_mtime, cfg.stat().st_mtime)
        api_cfg = module_dir / 'api' / 'celery_config.py'
        if api_cfg.exists():
            max_mtime = max(max_mtime, api_cfg.stat().st_mtime)
    return max_mtime


def fingerprint_equal(stored: Dict[str, float], current: Dict[str, float]) -> bool:
    """Проверка равенства fingerprint с учётом MTIME_TOLERANCE."""
    if set(stored.keys()) != set(current.keys()):
        return False
    for key in stored:
        if not mtime_equal(stored.get(key, 0), current.get(key, 0)):
            return False
    return True
