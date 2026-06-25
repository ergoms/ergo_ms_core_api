"""
Конфигурация CORS (Cross-Origin Resource Sharing) для Django API.

CORS позволяет веб-приложениям делать запросы к ресурсам с другого домена.
При CORS_ALLOW_CREDENTIALS = True нельзя использовать CORS_ALLOW_ALL_ORIGINS = True:
браузер запрещает Access-Control-Allow-Origin: * с учётными данными, поэтому задаём явный список.

Dev-origins собираются из _CORS_DEV_HOSTS и _CORS_DEV_PORTS (localhost/127.0.0.1 и порты 5173, 8001, 3000, 8080, 8000, 8003).
Для продакшена (в т.ч. внешние IP) в .env задают:
  - CORS_ALLOWED_ORIGINS — список полных origin'ов: http://localhost:5173, http://localhost:8001,...
  - или CORS_ALLOWED_ORIGIN_REGEXES — regex-шаблоны, например: ^https?://localhost(:\\d+)?$

При использовании прокси перед Django: запросы OPTIONS к /api/ должны проксироваться в Django;
ответ бэкенда не должен лишаться заголовков CORS.
"""

from src.config.env import env
from src.config.nginx_runtime import effective_cors_origins

CORS_ALLOW_ALL_ORIGINS = False

_CORS_DEV_PORTS = (5173, 8001, 3000, 8080, 8000, 8003)
_CORS_DEV_HOSTS = ('localhost', '127.0.0.1')
_default_origins = [
    f'http://{host}:{port}' for host in _CORS_DEV_HOSTS for port in _CORS_DEV_PORTS
]

CORS_ALLOWED_ORIGINS = effective_cors_origins(
    env.list('CORS_ALLOWED_ORIGINS', default=_default_origins),  # type: ignore[arg-type]
)

CORS_ALLOWED_ORIGIN_REGEXES = env.list(
    'CORS_ALLOWED_ORIGIN_REGEXES',
    default=[],  # type: ignore[arg-type]
)

CORS_ALLOW_CREDENTIALS = True
