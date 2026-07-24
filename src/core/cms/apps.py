"""
Файл конфигурации Django приложения/модуля CMS.


Этот файл содержит класс конфигурации приложения, который определяет основные настройки,
такие как имя приложения и настройки базы данных по умолчанию.

Класс `CmsConfig`:
    Определяет конфигурацию приложения CMS, включая:
    - Тип поля первичного ключа по умолчанию
    - Имя приложения в системе
"""
from django.apps import apps
from django.apps import AppConfig
from django.db.models.base import ModelBase

original_model_base = ModelBase.__new__

def new_model_base(cls, name, bases, attrs, **kwargs):
    if 'Meta' not in attrs:
        attrs['Meta'] = type('Meta', (), {})
    if not hasattr(attrs['Meta'], 'default_permissions'):
        attrs['Meta'].default_permissions = ()
    return original_model_base(cls, name, bases, attrs, **kwargs)

class CmsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'src.core.cms'
    label = 'cms'

    def ready(self):
        ModelBase.__new__ = new_model_base
