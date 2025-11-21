"""
Файл содержащий конфигурацию для отправки электронной почты через SMTP в Django-приложении.
Он включает настройки хоста, порта, использования TLS, учетных данных и адреса отправителя по умолчанию.
"""

from django.core.exceptions import ImproperlyConfigured
import logging
import os

from src.config.env import env
from src.config.settings.base import ENV_FILE_PATH

logger = logging.getLogger(__name__)

EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'

try:
    EMAIL_HOST = env.str('EMAIL_HOST')
    EMAIL_PORT = env.int('EMAIL_PORT')
    EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS')
    EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL')
    EMAIL_HOST_USER = env.str('EMAIL_HOST_USER')
    EMAIL_HOST_PASSWORD = env.str('EMAIL_HOST_PASSWORD')
    
    if not EMAIL_HOST or not EMAIL_PORT or not EMAIL_HOST_USER or not EMAIL_HOST_PASSWORD:
        missing = []
        if not EMAIL_HOST:
            missing.append('EMAIL_HOST')
        if not EMAIL_PORT:
            missing.append('EMAIL_PORT')
        if not EMAIL_HOST_USER:
            missing.append('EMAIL_HOST_USER')
        if not EMAIL_HOST_PASSWORD:
            missing.append('EMAIL_HOST_PASSWORD')
        
        logger.warning(f"Не все обязательные переменные SMTP установлены. Отсутствуют: {', '.join(missing)}")
    
    DEFAULT_FROM_EMAIL = EMAIL_HOST_USER if EMAIL_HOST_USER else None
except ImproperlyConfigured as e:
    logger.error(f"Ошибка конфигурации SMTP: {e}")
    logger.warning("Отправка email будет недоступна без правильной конфигурации SMTP")
except Exception as e:
    logger.error(f"Неожиданная ошибка при настройке SMTP: {e}", exc_info=True)
    logger.warning("Отправка email будет недоступна без правильной конфигурации SMTP")