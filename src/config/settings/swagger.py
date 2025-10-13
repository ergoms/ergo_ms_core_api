"""
Файл содержащий настройки Swagger для документации API.
"""

# Настройки Swagger для документации API.
SWAGGER_SETTINGS = {
    # Настройки для аутентификации через JWT Bearer Token
    'SECURITY_DEFINITIONS': {
        'Bearer': {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header',
        }
    },
    # Отключаем аутентификацию через сессии Django
    'USE_SESSION_AUTH': False,
    # Убираем URL для входа
    'LOGIN_URL': None,
    # Убираем URL для выхода
    'LOGOUT_URL': None,
}