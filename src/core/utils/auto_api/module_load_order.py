"""
Порядок загрузки модулей по ``requires`` из ``modules/<name>/integrations.yaml``.

Django вызывает ``AppConfig.ready()`` в порядке ``INSTALLED_APPS``.
Объявление ``requires`` (имена папок ``modules/<name>``) позволяет
топологически упорядочить модульные приложения: провайдеры ModuleBridge
раньше потребителей.

``extends`` — опциональные расширяющие модули: отсутствие не ошибка,
в топсорт не входят (чтобы не создавать циклы с ``requires`` расширителя).
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Dict, Iterable, List, Sequence, Tuple

from django.core.exceptions import ImproperlyConfigured

from src.core.utils.auto_api.module_integrations import (
    clear_module_integrations_cache,
    read_module_integrations,
)

logger = logging.getLogger('utils')


def _microservice_peer_names() -> frozenset[str]:
    """Имена модулей из MICROSERVICE_MODULES (доступны в другом процессе через мост)."""
    import os

    raw = os.environ.get('MICROSERVICE_MODULES', '') or ''
    return frozenset(m.strip() for m in raw.split(',') if m.strip())


def module_name_from_app(app_path: str) -> str | None:
    """``modules.<name>.api`` → ``<name>``; иначе None."""
    if not app_path.startswith('modules.'):
        return None
    parts = app_path.split('.')
    if len(parts) < 2:
        return None
    return parts[1]


def read_module_requires(module_name: str) -> Tuple[str, ...]:
    """Читает обязательные зависимости из ``modules/<name>/integrations.yaml``."""
    return read_module_integrations(module_name).requires


def read_module_extends(module_name: str) -> Tuple[str, ...]:
    """Читает расширяющие зависимости из ``modules/<name>/integrations.yaml``."""
    return read_module_integrations(module_name).extends


def _topo_sort_modules(
    module_names: Sequence[str],
    requires: Dict[str, Tuple[str, ...]],
) -> List[str]:
    """
    Топологическая сортировка имён модулей (Kahn).

    При равной готовности сохраняет исходный порядок (стабильность).
    """
    name_set = set(module_names)
    indegree = {name: 0 for name in module_names}
    edges: Dict[str, List[str]] = defaultdict(list)

    remote_peers = _microservice_peer_names()
    for name in module_names:
        for dep in requires.get(name, ()):
            if dep not in name_set:
                # MODULE_RUNTIME=microservice: зависимость в другом HTTP-процессе.
                if dep in remote_peers:
                    logger.debug(
                        'integrations.requires: %r → %r пропущен в этом процессе '
                        '(peer из MICROSERVICE_MODULES)',
                        name,
                        dep,
                    )
                    continue
                raise ImproperlyConfigured(
                    f"Модуль {name!r} объявил requires в integrations.yaml: "
                    f"зависимость {dep!r} не найдена среди установленных модулей "
                    f"(отключена в DISABLED_MODULES или отсутствует в modules/)."
                )
            edges[dep].append(name)
            indegree[name] += 1

    queue = deque([name for name in module_names if indegree[name] == 0])
    ordered: List[str] = []

    while queue:
        current = queue.popleft()
        ordered.append(current)
        for child in edges[current]:
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)

    if len(ordered) != len(module_names):
        leftover = [name for name in module_names if name not in ordered]
        cycle_hint = ', '.join(leftover)
        raise ImproperlyConfigured(
            f"Цикл в integrations.yaml requires между модулями: {cycle_hint}. "
            f"Проверьте modules/*/integrations.yaml."
        )
    return ordered


def _log_extends(module_order: Sequence[str], name_set: set[str]) -> None:
    for name in module_order:
        extends = read_module_extends(name)
        if not extends:
            continue
        for peer in extends:
            present = peer in name_set
            logger.debug(
                'integrations.extends: модуль %r расширяется %r (%s)',
                name,
                peer,
                'установлен' if present else 'отсутствует',
            )


def sort_discovered_apps(apps: Iterable[str]) -> List[str]:
    """
    Сортирует discovered apps: ядро как было, модули — по requires из integrations.yaml.

    Приложения одного модуля сохраняют относительный порядок discovery.
    """
    apps_list = list(apps)
    core_apps = [app for app in apps_list if not app.startswith('modules.')]
    module_apps = [app for app in apps_list if app.startswith('modules.')]

    by_module: Dict[str, List[str]] = {}
    module_order: List[str] = []
    for app in module_apps:
        name = module_name_from_app(app)
        if name is None:
            core_apps.append(app)
            continue
        if name not in by_module:
            by_module[name] = []
            module_order.append(name)
        by_module[name].append(app)

    clear_module_integrations_cache()
    requires = {name: read_module_requires(name) for name in module_order}
    sorted_names = _topo_sort_modules(module_order, requires)
    _log_extends(module_order, set(module_order))

    result = list(core_apps)
    for name in sorted_names:
        result.extend(by_module[name])

    if requires and any(requires.values()):
        logger.debug(
            'Discovered apps: порядок модулей по integrations.requires: %s',
            ' → '.join(sorted_names),
        )
    return result
