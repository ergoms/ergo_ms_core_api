"""
Настройки для изолированного тестирования модулей.

Загружает только ядро + тестируемый модуль + его зависимости.
Целевой модуль определяется через переменную окружения TEST_TARGET_MODULE.

Если TEST_TARGET_MODULE не задан или TEST_FULL_APPS=1,
загружаются все модули (стандартное поведение).
"""

import importlib
import os
import sys
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.config.patterns.test')

from src.config.env import env

SECRET_KEY = env.str('API_SECRET_KEY')
DEBUG = True
ALLOWED_HOSTS = ['*']

settings_dir = Path(__file__).parent.parent / 'settings'

deferred_settings = {'celery_beat', 'jupyter', 'apps'}

for file_path in settings_dir.glob('*.py'):
    if file_path.name in ('__init__.py', '__pycache__'):
        continue
    module_name = file_path.stem
    if module_name in deferred_settings:
        continue
    module_path = f'src.config.settings.{module_name}'
    try:
        module = importlib.import_module(module_path)
        globals().update({
            name: getattr(module, name)
            for name in dir(module)
            if not name.startswith('_')
        })
    except ImportError as e:
        print(f"Ошибка импорта модуля {module_path}: {e}")

from src.config.settings.user_swappable import resolve_auth_user_model

_resolved_auth_user_model = resolve_auth_user_model(DATABASES)
if _resolved_auth_user_model:
    AUTH_USER_MODEL = _resolved_auth_user_model

target_module = os.environ.get('TEST_TARGET_MODULE')
use_full_apps = os.environ.get('TEST_FULL_APPS', '').lower() in ('1', 'true', 'yes')

if target_module and not use_full_apps:
    from src.core.utils.test_isolation.module_deps import get_isolated_apps
    ALL_MODULES = get_isolated_apps(target_module)
    _isolation_mode = True
else:
    from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps
    ALL_MODULES = get_discovered_apps(use_cache=True)
    _isolation_mode = False

INSTALLED_APPS = ALL_MODULES + [
    'daphne',
    'channels',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_extensions',
    'rest_framework',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'drf_yasg',
    'django_celery_beat',
]

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer"
    }
}

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'src.core.utils.middleware.security_headers_middleware.SecurityHeadersMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'src.core.utils.middleware.session_context_middleware.SessionContextMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware'
]

if _isolation_mode:
    print(f"[TEST] Изолированный режим: модуль '{target_module}'")
    print(f"[TEST] Загружено приложений: {len(ALL_MODULES)}")
