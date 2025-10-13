"""
Файл содержащий конфигурацию статических и медиа файлов, а также логов для Django-приложения.
Он включает настройки URL и корневых директорий для статических файлов, медиа файлов и логов.
"""

import os

from src.config.settings.base import API_DIR, SYSTEM_DIR, BASE_DIR

CORE_DIR = BASE_DIR / 'core'

VIRTUAL_ENV_DIR = SYSTEM_DIR / 'virtual_env'

# URL для доступа к статическим файлам.
STATIC_URL = '/static/'

# Корневая директория для статических файлов.
STATIC_ROOT = os.path.join(API_DIR, 'static')

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

# Корневая директория для ресурсов.
RESOURCES_DIR = os.path.join(VIRTUAL_ENV_DIR, 'resources')

# Корневая директория для обученных моделей.
TRAINED_MODELS_PATH = os.path.join(VIRTUAL_ENV_DIR, 'trained_models')

# Корневая директория для сторонних программ.
PACKAGES_PATH = os.path.join(VIRTUAL_ENV_DIR, 'packages')

# Корневая директория для модулей.
MODULES_DIR = os.path.join(SYSTEM_DIR, 'modules')

# Путь к основному .env файлу (в корне проекта SYSTEM_DIR).
ENV_FILE_PATH = os.path.join(SYSTEM_DIR, '.env')