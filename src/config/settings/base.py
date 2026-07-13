"""
Файл содержащий базовую конфигурацию для Django-приложения.
Он включает настройки базового каталога проекта.
"""

import os
from pathlib import Path

from src.config.nginx_runtime import (
    effective_media_public_host,
    effective_media_public_port,
    media_api_internal_base_url,
    media_api_public_base_url,
    nginx_use_https,
)

"""
Определяет базовый каталог проекта.

BASE_DIR используется для построения путей к различным ресурсам проекта, таким как шаблоны, статические файлы и т.д.
"""
# Получаем путь к корневой директории проекта (ergo_ms/api/src)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Получаем путь к директории api (ergo_ms/api)
API_DIR = Path(__file__).resolve().parent.parent.parent.parent

# Получаем путь к директории системы (ergo_ms/)
SYSTEM_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent.parent

CORE_DIR = BASE_DIR / 'core'

# Корневая директория для модулей.
MODULES_DIR = SYSTEM_DIR / 'modules'

# Путь к основному .env файлу (в корне проекта SYSTEM_DIR).
ENV_FILE_PATH = SYSTEM_DIR / '.env'

# Корневая директория для виртуального окружения.
VIRTUAL_ENV_DIR = SYSTEM_DIR / 'virtual_env'

# Корневая директория для ресурсов.
RESOURCES_DIR = VIRTUAL_ENV_DIR / 'resources'

# Корневая директория для обученных моделей.
TRAINED_MODELS_PATH = VIRTUAL_ENV_DIR / 'trained_models'

# Корневая директория для сторонних программ.
PACKAGES_PATH = VIRTUAL_ENV_DIR / 'packages'

# URL для доступа к статическим файлам.
STATIC_URL = '/static/'

# Корневая директория для статических файлов.
STATIC_ROOT = VIRTUAL_ENV_DIR / 'static_api'

# URL для доступа к медиа файлам.
MEDIA_URL = '/media/'

# Корневая директория для медиа файлов.
MEDIA_ROOT = os.path.join(SYSTEM_DIR, 'media')

# Корневая директория для сгенерированных документов.
GENERATED_DOCUMENTS_DIR = Path(MEDIA_ROOT) / 'generated_docs'

# URL для доступа к логам.
LOGS_URL = '/logs/'

# Корневая директория для логов (ERGO_LOGS_DIR в .env или <корень>/logs).
from src.config.log_paths import resolve_logs_root

LOGS_ROOT = str(resolve_logs_root(SYSTEM_DIR))

# Хранилище для статических файлов, использующее Whitenoise для сжатия и кэширования.
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

STORAGES = {
    'default': {
        'BACKEND': 'src.core.utils.media_storage.MediaApiStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Media API (CDN / file server)
MEDIA_API_PUBLIC_BASE_URL = media_api_public_base_url()
MEDIA_API_INTERNAL_BASE_URL = media_api_internal_base_url()
# Legacy-поля (деплой-скрипты, обратная совместимость; в .env можно не задавать)
MEDIA_API_HOST = effective_media_public_host('localhost')
MEDIA_API_PORT = int(effective_media_public_port('8003'))
MEDIA_API_PROTOCOL = 'https' if nginx_use_https() else os.getenv('MEDIA_API_PROTOCOL', 'http')
MEDIA_URL_EXPIRATION = int(os.getenv('MEDIA_URL_EXPIRATION', '3600'))
MEDIA_UPLOAD_MAX_SIZE = int(os.getenv('MEDIA_UPLOAD_MAX_SIZE', '104857600'))
MEDIA_UPLOAD_TOKEN_EXPIRATION = int(os.getenv('MEDIA_UPLOAD_TOKEN_EXPIRATION', '300'))

# Режим доступа core/api к файлам: local (прямая ФС) или remote (HTTP к media_api)
MEDIA_ACCESS_MODE = os.getenv('MEDIA_ACCESS_MODE', 'local').strip().lower()
MEDIA_API_INTERNAL_KEY = os.getenv('MEDIA_API_INTERNAL_KEY', '').strip()

# Compute-пайплайн (см. core/utils/media_client/pipeline.py, scratch.py)
# Scratch — эфемерные файлы обработки (никогда в БД и не в signed URL)
MEDIA_SCRATCH_ROOT = os.getenv('MEDIA_SCRATCH_ROOT', '').strip() or str(VIRTUAL_ENV_DIR / 'cache' / 'scratch')
# Cache — локальные копии canonical-файлов при MEDIA_ACCESS_MODE=remote (localize)
MEDIA_CACHE_ROOT = os.getenv('MEDIA_CACHE_ROOT', '').strip() or str(VIRTUAL_ENV_DIR / 'cache' / 'media')