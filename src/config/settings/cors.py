"""
Файл содержащий конфигурацию для настройки CORS (Cross-Origin Resource Sharing) в Django-приложении.
CORS позволяет веб-приложениям делать запросы к ресурсам на другом домене.

При CORS_ALLOW_CREDENTIALS = True нельзя использовать CORS_ALLOW_ALL_ORIGINS = True:
браузер запрещает заголовок Access-Control-Allow-Origin: * с учётными данными.
Поэтому задаём явный список разрешённых источников.
"""

from src.config.env import env

CORS_ALLOW_ALL_ORIGINS = False

CORS_ALLOWED_ORIGINS = env.list(
    'CORS_ALLOWED_ORIGINS',
    default=[
        'http://localhost:5173',
        'http://127.0.0.1:5173',
        'http://localhost:8001',
        'http://127.0.0.1:8001',
        'http://localhost:3000',
        'http://127.0.0.1:3000',
        'http://localhost:8080',
        'http://127.0.0.1:8080',
        'http://localhost:8000',
        'http://127.0.0.1:8000',
        'http://localhost:8003',
        'http://127.0.0.1:8003',
    ],
)

CORS_ALLOW_CREDENTIALS = True
