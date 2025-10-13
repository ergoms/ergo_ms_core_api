"""
Файл конфигурации Django приложения utils.

Этот файл содержит класс конфигурации приложения, который определяет основные настройки,
такие как имя приложения и настройки базы данных по умолчанию.

Класс `UtilsConfig`:
    Определяет конфигурацию приложения utils, включая:
    - Тип поля первичного ключа по умолчанию
    - Имя приложения в системе
"""

from django.apps import AppConfig

class UtilsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.utils'
    label = 'utils'