"""
Разрешение имени модуля для Celery при nested Django-apps.

Пути вида modules.<catalog>.api.<subapp> должны:
- проверять disabled по catalog (папка modules/<catalog>);
- хранить конфиг под уникальным config_key;
- создавать логгеры celery.module.<catalog>.* (и subapp при необходимости).
"""

from typing import Optional, Tuple


def resolve_celery_app_identity(app_path: str) -> Optional[Tuple[str, str, str]]:
    """
    Возвращает (config_key, catalog_name, logger_module_name) или None.

    - modules.foo.api -> (foo, foo, foo)
    - modules.foo.api.bar -> (foo_bar, foo, foo)
    """
    parts = app_path.split('.')
    if len(parts) < 2 or parts[0] != 'modules':
        return None

    catalog_name = parts[1]

    if len(parts) >= 4 and parts[2] == 'api':
        subapp = parts[3]
        config_key = f'{catalog_name}_{subapp}'
        return config_key, catalog_name, catalog_name

    if len(parts) >= 3 and parts[2] == 'api':
        return catalog_name, catalog_name, catalog_name

    # Нестандартный путь modules.* — fallback на последний сегмент
    fallback = parts[-1]
    return fallback, catalog_name, catalog_name
