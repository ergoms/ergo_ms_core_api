"""
Явная загрузка модулей src.config.settings в patterns (local / test).

Fail-fast при ImportError — не глотать ошибку через print.
"""

from __future__ import annotations

import importlib
import logging
from typing import Any, Iterable

logger = logging.getLogger(__name__)

# Алфавитный порядок как у прежнего glob('*.py'); deferred исключаются вызывающим.
SETTINGS_MODULES: tuple[str, ...] = (
    'apps',
    'audit',
    'auth',
    'base',
    'bridge',
    'cache',
    'celery',
    'celery_beat',
    'channel_layers',
    'client_monitoring',
    'cors',
    'database',
    'drf',
    'geoip',
    'jupyter',
    'localization',
    'logger',
    'menu',
    'notifications',
    'password',
    'password_reset',
    'profile',
    'realtime',
    'registration',
    'security_headers',
    'server',
    'smtp',
    'swagger',
    'user_swappable',
)


def load_settings_modules(
    target: dict[str, Any],
    *,
    deferred: Iterable[str] = (),
    skip: Iterable[str] = (),
) -> None:
    """
    Импортирует модули settings и пишет публичные имена в target (обычно globals()).

    :param deferred: модули, пропускаемые для текущего процесса (celery_beat / jupyter / …)
    :param skip: уже загруженные модули (например logger до dictConfig)
    """
    deferred_set = set(deferred)
    skip_set = set(skip)

    for module_name in SETTINGS_MODULES:
        if module_name in deferred_set or module_name in skip_set:
            continue
        module_path = f'src.config.settings.{module_name}'
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            logger.exception('Ошибка импорта модуля настроек %s', module_path)
            raise
        target.update({
            name: getattr(module, name)
            for name in dir(module)
            if not name.startswith('_')
        })
