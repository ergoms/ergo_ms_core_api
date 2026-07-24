"""
Файл содержащий конфигурацию баз данных для Django-приложения.
Поддерживает множественные подключения к разным типам СУБД через YAML конфигурацию.
Использует централизованную объектно-ориентированную систему управления БД.
"""

import logging
import os
import sys

from src.config.settings.base import SYSTEM_DIR, RESOURCES_DIR
from src.config.env import env

from src.core.utils.database.config_manager import DjangoDatabaseConfigLoader

logger = logging.getLogger('config.database')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

_test_connections_env = env.bool('DATABASE_TEST_CONNECTIONS', default=True)
_argv_lower = ' '.join(getattr(sys, 'argv', [])).lower()
_is_autoreload_parent = (
    ('runserver' in _argv_lower or 'dev' in _argv_lower)
    and os.environ.get('RUN_MAIN') != 'true'
)
test_connections = _test_connections_env and not _is_autoreload_parent

db_loader = DjangoDatabaseConfigLoader(
    system_dir=SYSTEM_DIR,
    resources_dir=RESOURCES_DIR,
    test_connections=test_connections
)

# Загружаем конфигурацию БД
try:
    DATABASES = db_loader.load_config()
    logger.info(f"Загружено {len(DATABASES)} конфигураций БД: {', '.join(DATABASES.keys())}")
except Exception as e:
    logger.error(f"Критическая ошибка при загрузке БД: {str(e)}")
    # Fallback на SQLite
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': str(RESOURCES_DIR / 'db.sqlite3'),
        }
    }
    logger.warning("Используется fallback конфигурация SQLite")