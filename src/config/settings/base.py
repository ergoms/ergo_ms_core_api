"""
Файл содержащий базовую конфигурацию для Django-приложения.
Он включает настройки базового каталога проекта.
"""

import os
from pathlib import Path

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

# URL для доступа к логам.
LOGS_URL = '/logs/'

# Корневая директория для логов.
LOGS_ROOT = os.path.join(SYSTEM_DIR, 'logs')

# Хранилище для статических файлов, использующее Whitenoise для сжатия и кэширования.
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Ограничения задач
TASKS_MAX_ATTACHMENT_SIZE_MB = int(os.getenv('TASKS_MAX_ATTACHMENT_SIZE_MB', '25'))
TASKS_MAX_ATTACHMENT_SIZE_BYTES = TASKS_MAX_ATTACHMENT_SIZE_MB * 1024 * 1024