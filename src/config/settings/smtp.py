"""
Файл содержащий конфигурацию для отправки электронной почты через SMTP в Django-приложении.
Он включает настройки хоста, порта, использования TLS, учетных данных и адреса отправителя по умолчанию.
"""

from django.core.exceptions import ImproperlyConfigured

from src.config.env import env

# Backend приложения для отправки электронной почты через SMTP.
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

try:
    # Хост SMTP-сервера.
    EMAIL_HOST = env.str('EMAIL_HOST')

    # Порт SMTP-сервера.
    EMAIL_PORT = env.str('EMAIL_PORT')

    # Флаг, указывающий, используется ли TLS для соединения с SMTP-сервером.
    EMAIL_USE_TLS = env.str('EMAIL_USE_TLS')

    # Пользователь для аутентификации на SMTP-сервере.
    EMAIL_HOST_USER = env.str('EMAIL_HOST_USER')

    # Пароль для аутентификации на SMTP-сервере, полученный из переменной окружения.
    EMAIL_HOST_PASSWORD = env.str('EMAIL_HOST_PASSWORD')

    # Адрес отправителя по умолчанию, используется тот же, что и для аутентификации на SMTP-сервере.
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER
except ImproperlyConfigured:
    # В случае ошибки конфигурации, пропускаем настройку SMTP-сервера.
    pass