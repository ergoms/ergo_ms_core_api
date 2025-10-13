"""
Файл для настройки маршрутов документации Django-API с использованием библиотеки drf-yasg.

Он создает представление схемы API, используя информацию из переменных окружения,
и определяет маршруты для доступа к документации в форматах JSON, YAML, Swagger UI и ReDoc.
"""

from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.authentication import JWTAuthentication

from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from django.urls import re_path

from src.config.env import env

# Получаем название системы из переменных окружения
system_title = env.str('SYSTEM_TITLE', default='API')

# Создаем представление схемы API
schema_view = get_schema_view(
    openapi.Info(
        title=f"{system_title} API",
        default_version='v1',
        description="API системы управления организациями",
        terms_of_service="https://www.google.com/policies/terms/",
    ),
    public=True,
    permission_classes=(AllowAny,),
    authentication_classes=[JWTAuthentication],
)

# Определяем маршруты для доступа к документации API
urlpatterns = [
    re_path(
        r"^swagger(?P<format>\.json|\.yaml)$",
        schema_view.without_ui(cache_timeout=0),
        name="schema-json",
    ),
    re_path(
        r"^swagger/$",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    re_path(
        r"^redoc/$", 
        schema_view.with_ui("redoc", cache_timeout=0), 
        name="schema-redoc",
    ),
]