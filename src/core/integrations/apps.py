"""
AppConfig для ``src.core.integrations``.

На этапе ``ready()``:

1. Проверяет, что ``BRIDGE_TRANSPORT`` / ``BRIDGE_EVENT_BUS`` остаются
   ``local`` (удалённые транспорты не поддерживаются).
2. Устанавливает runtime-страж изоляции модулей
   (см. :mod:`src.core.integrations.isolation`) согласно настройке
   ``BRIDGE_ISOLATION`` (``'off' | 'warn' | 'raise'``).

При ``local`` ``ModuleBridge.configure`` не вызывается — это важно, чтобы
не сбросить уже зарегистрированные провайдеры (порядок ``ready()``
Django-приложений строго не гарантируется).
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
        from src.core.utils.django_cli import is_lean_schema_cli

        # migrate/makemigrations: Local* bridge по умолчанию достаточен, audit hook не нужен
        if is_lean_schema_cli():
            return

        self._ensure_local_bridge()
        self._install_isolation_guard()

    @staticmethod
    def _ensure_local_bridge() -> None:
        transport_name = (getattr(settings, 'BRIDGE_TRANSPORT', 'local') or 'local').strip().lower()
        event_bus_name = (getattr(settings, 'BRIDGE_EVENT_BUS', 'local') or 'local').strip().lower()

        if transport_name != 'local':
            raise ImproperlyConfigured(
                f"BRIDGE_TRANSPORT={transport_name!r} не поддерживается. "
                f"Допустимо только 'local'."
            )
        if event_bus_name != 'local':
            raise ImproperlyConfigured(
                f"BRIDGE_EVENT_BUS={event_bus_name!r} не поддерживается. "
                f"Допустимо только 'local'."
            )

        logger.debug(
            "ModuleBridge stays on default Local* implementations"
        )

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
