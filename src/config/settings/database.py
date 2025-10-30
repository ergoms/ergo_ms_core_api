"""
Файл содержащий конфигурацию баз данных для Django-приложения.
Поддерживает множественные подключения к разным типам СУБД через YAML конфигурацию.
Использует централизованную объектно-ориентированную систему управления БД.
"""

import logging.config

from src.config.settings.logger import LOGGING
from src.config.settings.base import SYSTEM_DIR, RESOURCES_DIR

# Импортируем централизованный менеджер БД
from src.core.utils.database.config_manager import DjangoDatabaseConfigLoader

# Явная инициализация логирования
logging.config.dictConfig(LOGGING)

# Настройка логгера
logger = logging.getLogger('config.database')

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Создаем загрузчик конфигурации Django БД
db_loader = DjangoDatabaseConfigLoader(
    system_dir=SYSTEM_DIR,
    resources_dir=RESOURCES_DIR,
    test_connections=True  # Тестируем подключения при загрузке
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