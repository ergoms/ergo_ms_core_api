"""
Этот файл содержит настройки установленных приложений и middleware для Django-приложения.

Использует кэшированный discovery приложений (discovered_apps_cache) — результат
сохраняется в файл и пересчитывается только при изменении core/ или modules/.
"""

from src.core.utils.auto_api.discovered_apps_cache import get_discovered_apps

ALL_MODULES = get_discovered_apps(use_cache=True)

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