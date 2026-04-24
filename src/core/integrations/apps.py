"""
AppConfig для ``src.core.integrations``.

На этапе ``ready()``:

1. Подменяет in-process реализации ``ModuleBridge`` на удалённые
   (HTTP / Celery), если это указано в Django settings
   (``BRIDGE_TRANSPORT`` / ``BRIDGE_EVENT_BUS``).
2. Устанавливает runtime-страж изоляции модулей
   (см. :mod:`src.core.integrations.isolation`) согласно настройке
   ``BRIDGE_ISOLATION`` (``'off' | 'warn' | 'raise'``).

Если транспорт и шина остаются ``'local'`` (по умолчанию),
``ModuleBridge.configure`` не вызывается — это важно, чтобы не сбросить
уже зарегистрированные провайдеры (порядок ``ready()`` Django-приложений
строго не гарантируется).
"""

from __future__ import annotations

import logging
from pathlib import Path

from django.apps import AppConfig
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .isolation import VALID_MODES, find_modules_dir, install_isolation_audit_hook

logger = logging.getLogger('integrations.bridge')


class IntegrationsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.integrations'
    label = 'core_integrations'
    verbose_name = 'Module Bridge'

    def ready(self) -> None:
        from .bridge import ModuleBridge

        transport_name = getattr(settings, 'BRIDGE_TRANSPORT', 'local')
        event_bus_name = getattr(settings, 'BRIDGE_EVENT_BUS', 'local')

        new_transport = self._build_transport(transport_name)
        new_event_bus = self._build_event_bus(event_bus_name)

        if new_transport is None and new_event_bus is None:
            logger.debug(
                "ModuleBridge stays on default Local* implementations"
            )
        else:
            ModuleBridge.configure(
                transport=new_transport,
                event_bus=new_event_bus,
            )

        self._install_isolation_guard()

    @staticmethod
    def _install_isolation_guard() -> None:
        mode = (getattr(settings, 'BRIDGE_ISOLATION', 'warn') or 'warn').strip().lower()
        if mode not in VALID_MODES:
            raise ImproperlyConfigured(
                f"Unknown BRIDGE_ISOLATION value: {mode!r}. "
                f"Expected one of {VALID_MODES}."
            )

        modules_dir = getattr(settings, 'MODULES_DIR', None)
        if modules_dir is None:
            base_dir = getattr(settings, 'BASE_DIR', None)
            if base_dir is not None:
                modules_dir = find_modules_dir(Path(base_dir))

        install_isolation_audit_hook(mode=mode, modules_dir=modules_dir)

    @staticmethod
    def _build_transport(name: str):
        normalized = (name or 'local').strip().lower()
        if normalized == 'local':
            return None
        if normalized == 'http':
            from .transports.http import HttpTransport

            return HttpTransport()
        raise ImproperlyConfigured(
            f"Unknown BRIDGE_TRANSPORT value: {name!r}. "
            f"Expected 'local' or 'http'."
        )

    @staticmethod
    def _build_event_bus(name: str):
        normalized = (name or 'local').strip().lower()
        if normalized == 'local':
            return None
        if normalized == 'celery':
            from .transports.celery_bus import CeleryEventBus

            return CeleryEventBus()
        raise ImproperlyConfigured(
            f"Unknown BRIDGE_EVENT_BUS value: {name!r}. "
            f"Expected 'local' or 'celery'."
        )
