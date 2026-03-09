"""
Минимальные настройки для warmup_caches.

- Без подключения к БД (in-memory SQLite)
- Минимальный INSTALLED_APPS
- Отключены тяжёлые проверки
- Ускорение django.setup() для прогрева кэшей
"""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'src.config.patterns.warmup')
os.environ['DJANGO_SKIP_MIGRATIONS_CHECK'] = '1'

from src.config.settings.base import CORE_DIR, MODULES_DIR, SYSTEM_DIR, VIRTUAL_ENV_DIR
from src.config.settings.logger import LOGGING
from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps

SECRET_KEY = os.environ.get('API_SECRET_KEY', 'warmup-dummy-secret-key')

DEBUG = False
ALLOWED_HOSTS = ['localhost']

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django_celery_beat',
] + get_discovered_apps(use_cache=True)

MIDDLEWARE = []
ROOT_URLCONF = 'src.config.urls_warmup'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

LOGGING = LOGGING
