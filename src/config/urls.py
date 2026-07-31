"""
Файл для определения маршрутов URL для Django-API-приложения.

Он использует функцию `path` из `django.urls` для определения маршрутов и функцию `include`
для включения URL-конфигураций из других модулей. Автоматическое обнаружение URL-конфигураций
ядра и модулей выполняется через класс `ModuleDiscoverer`.
"""

from src.core.utils.auto_api.auto_config import ModuleDiscoverer
from src.config.settings.base import DJANGO_CORE_DIR, MODULES_DIR, BASE_DIR
from src.core.utils.path_utils import convert_path_to_dot_notation

urlpatterns = []

discoverer = ModuleDiscoverer()

# Добавляем URL-конфигурации ядра, автоматически обнаруженные в DJANGO_CORE_DIR
core_relative_path = DJANGO_CORE_DIR.relative_to(BASE_DIR.parent)
core_prefix = convert_path_to_dot_notation(core_relative_path)
core_urlpatterns: list = []
discoverer._recursively_find_urls(str(DJANGO_CORE_DIR), core_prefix, "", core_urlpatterns)
urlpatterns += core_urlpatterns

# Добавляем URL-конфигурации модулей, автоматически обнаруженные в директории MODULES_DIR
modules_urlpatterns: list = []
discoverer._find_modules_urls(str(MODULES_DIR), modules_urlpatterns)
urlpatterns += modules_urlpatterns