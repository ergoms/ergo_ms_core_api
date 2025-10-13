"""
Файл для определения маршрутов URL для Django-API-приложения.

Он использует функцию `path` из `django.urls` для определения маршрутов и функцию `include`
для включения URL-конфигураций из других модулей. Также используется функция
`discover_installed_app_urls` для автоматического обнаружения и включения URL-конфигураций
из модулей, находящихся в директориях `CORE_DIR` и`MODULES_DIR`.
"""

from src.core.utils.auto_api.auto_config import discover_installed_app_urls
from src.config.settings.apps import CORE_DIR, MODULES_DIR
from src.core.utils.methods import convert_path_to_dot_notation

urlpatterns = []

# Добавляем URL-конфигурации ядра, автоматически 
# обнаруженные в директории CORE_DIR
core_prefix = convert_path_to_dot_notation(CORE_DIR)
core_urlpatterns = discover_installed_app_urls(CORE_DIR, prefix=core_prefix)
urlpatterns += core_urlpatterns

# Добавляем URL-конфигурации модулей, автоматически 
# обнаруженные в директории MODULES_DIR
modules_prefix = convert_path_to_dot_notation(MODULES_DIR)
modules_urlpatterns = discover_installed_app_urls(MODULES_DIR, prefix=modules_prefix)
urlpatterns += modules_urlpatterns