"""
Файл объединяющий локальные настройки для Django-приложения.

Импортирует настройки из settings. Модули celery_beat и jupyter
загружаются только для соответствующих процессов (отложенная загрузка).
"""

import logging.config
import sys

# До загрузки settings: иначе celery.py логирует до dictConfig (алфавитный порядок).
from src.config.settings.logger import LOGGING
from src.config.settings_loader import load_settings_modules

logging.config.dictConfig(LOGGING)

argv_joined = ' '.join(sys.argv).lower()
is_celery_beat = 'beat' in argv_joined
is_jupyter_cmd = 'jupyter' in argv_joined or 'notebook' in argv_joined

deferred_settings = set()
if not is_celery_beat:
    deferred_settings.add('celery_beat')
if not is_jupyter_cmd:
    deferred_settings.add('jupyter')

load_settings_modules(
    globals(),
    deferred=deferred_settings,
    skip={'logger'},
)

from src.config.settings.user_swappable import resolve_auth_user_model

_resolved_auth_user_model = resolve_auth_user_model(DATABASES)
if _resolved_auth_user_model:
    AUTH_USER_MODEL = _resolved_auth_user_model
