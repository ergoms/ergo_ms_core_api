"""
Файл содержащий конфигурацию аутентификации и авторизации для Django-приложения.
Он включает настройки для валидации паролей, ограничения запросов, JWT-аутентификации
и документации Swagger.

Конфигурация включает:
- Валидаторы паролей
- Ограничения запросов для анонимных и аутентифицированных пользователей
- Настройки JWT-аутентификации
- Настройки Swagger для документации API
"""

from datetime import timedelta

from django.conf import settings

from src.config.env import env

# Список валидаторов паролей, используемых для проверки паролей пользователей.
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Настройка ограничения запросов для анонимных и аутентифицированных пользователей.
THROTTLE_RATES_ANON = env.str('API_THROTTLE_RATES_ANON', default='10/minute')
THROTTLE_RATES_USER = env.str('API_THROTTLE_RATES_USER', default='5000/hour')

# Конфигурация Django REST Framework.
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': THROTTLE_RATES_ANON,
        'user': THROTTLE_RATES_USER,
    },
}

# Установка настроек REST_FRAMEWORK глобально
if not hasattr(settings, 'REST_FRAMEWORK'):
    setattr(settings, 'REST_FRAMEWORK', REST_FRAMEWORK)

# Настройка время жизни токенов доступа и обновления.
ACCESS_TOKEN_LIFETIME = env.int('API_ACCESS_TOKEN_LIFETIME', default=30)
REFRESH_TOKEN_LIFETIME = env.int('API_REFRESH_TOKEN_LIFETIME', default=1440)

# Конфигурация JWT-аутентификации.
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=ACCESS_TOKEN_LIFETIME),
    'REFRESH_TOKEN_LIFETIME': timedelta(minutes=REFRESH_TOKEN_LIFETIME),
    'ROTATE_REFRESH_TOKENS': False,
    'BLACKLIST_AFTER_ROTATION': True,
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': env.str('API_SECRET_KEY'),
    'VERIFYING_KEY': None,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}