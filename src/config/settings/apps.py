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

# Обнаруживаем и устанавливаем основные и сторонние модули через ModuleDiscoverer
discoverer = ModuleDiscoverer()

CORE: list[str] = []
discoverer._recursively_find_apps(str(CORE_DIR), 'src.core', CORE)

MODULES: list[str] = []
discoverer._find_modules_apps(str(MODULES_DIR), MODULES)

ALL_MODULES = CORE + MODULES

# Определяем список установленных приложений
INSTALLED_APPS = ALL_MODULES + [
    'daphne',
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

# Определяем список middleware
MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware'
]