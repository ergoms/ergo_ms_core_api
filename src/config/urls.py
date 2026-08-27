"""
Файл для определения маршрутов URL для Django-API-приложения.

Он использует функцию `path` из `django.urls` для определения маршрутов и функцию `include`
для включения URL-конфигураций из других модулей. Список маршрутов ядра и модулей
берётся из файлового кэша (как discovered_apps); include() остаётся ленивым.
"""

from django.urls import include, path

from src.core.utils.auto_api.discovered_urls_cache import get_discovered_url_entries
from src.core.utils.module_registry import is_slim_module_process

urlpatterns = []
if not is_slim_module_process():
    from src.core.system.jupyter_gate import JupyterAccessView

    urlpatterns.append(
        path('internal/jupyter-access/', JupyterAccessView.as_view(), name='jupyter-access'),
    )

for route, dotted_module in get_discovered_url_entries():
    urlpatterns.append(path(route, include(dotted_module)))
