"""
Этот файл содержит настройки установленных приложений и middleware для Django-приложения.

Он использует функцию `discover_installed_apps` для автоматического обнаружения приложений в указанных директориях
и добавляет их в список установленных приложений. Также настраивает middleware, включая CORS middleware.

Middleware (промежуточное ПО) в контексте Django — это компонент, который обрабатывает запросы и ответы в 
процессе их прохождения через Django-приложение. Middleware позволяет выполнять различные задачи, такие 
как аутентификация, логирование, обработка ошибок, кэширование и многое другое, без необходимости изменять 
основной код приложения.
"""

from src.core.utils.auto_api.auto_config import ModuleDiscoverer
from src.config.settings.base import MODULES_DIR, CORE_DIR


def discover_installed_apps() -> list[str]:
    """
    Ленивая обертка над ModuleDiscoverer.

    ВАЖНО:
    - Не выполняем discovery на уровне модуля settings, чтобы избежать
      ранних импортов приложений во время `apps.populate()`.
    - Вызывается Django только один раз при построении INSTALLED_APPS.
    """
    discoverer = ModuleDiscoverer()

    core_apps: list[str] = []
    discoverer._recursively_find_apps(str(CORE_DIR), 'src.core', core_apps)

    module_apps: list[str] = []
    discoverer._find_modules_apps(str(MODULES_DIR), module_apps)

    return core_apps + module_apps


ALL_MODULES = discover_installed_apps()

# Определяем список установленных приложений
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

# Определяем список middleware
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'src.core.utils.middleware.organization_middleware.OrganizationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware'
]