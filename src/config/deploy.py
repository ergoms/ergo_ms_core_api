"""
Режим развёртывания API (development / production).

Единая точка для выбора settings, bind host/port и команд запуска сервера.
Используется скриптами (start_api.py), manage.py, ASGI/WSGI и Django settings.
"""

from __future__ import annotations

import sys
from typing import List

from src.config.env import env
from src.config.nginx_runtime import effective_api_bind_host

DEVELOPMENT = 'development'
PRODUCTION = 'production'

ASGI_APPLICATION = 'src.config.asgi:application'
SETTINGS_DEVELOPMENT = 'src.config.patterns.development'
SETTINGS_PRODUCTION = 'src.config.patterns.production'


def get_deploy_type() -> str:
    """ERGO_ENV; явный API_DEPLOY_TYPE перекрывает."""
    from src.config.ergo_runtime import api_deploy_type

    return api_deploy_type()


def is_production() -> bool:
    return get_deploy_type() == PRODUCTION


def is_development() -> bool:
    return not is_production()


def get_settings_module() -> str:
    if is_production():
        return SETTINGS_PRODUCTION
    return SETTINGS_DEVELOPMENT


def get_api_bind_host(default: str = 'localhost') -> str:
    return effective_api_bind_host(default)


def get_api_bind_port(default: str = '8000') -> str:
    return env.str('API_PORT', default=default)


def build_daphne_command(python_executable: str | None = None) -> List[str]:
    """Команда production-запуска API через daphne (ASGI, без autoreload)."""
    import os

    from src.config.log_format import DAPHNE_LOG_FMT

    exe = python_executable or sys.executable
    # NCSA access daphne отключён (в os.devnull): единый HTTP-лог — AccessLogMiddleware.
    return [
        exe,
        '-m',
        'daphne',
        '-b',
        get_api_bind_host(),
        '-p',
        get_api_bind_port(),
        '--access-log',
        os.devnull,
        '--log-fmt',
        DAPHNE_LOG_FMT,
        ASGI_APPLICATION,
    ]


def build_dev_command(python_executable: str | None = None) -> List[str]:
    """Команда development-запуска API (runserver с autoreload через commands dev)."""
    exe = python_executable or sys.executable
    return [exe, '-m', 'commands', 'dev']
