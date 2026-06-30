"""
Файл для настройки маршрутов документации Django-API с использованием библиотеки drf-yasg.

Он создает представление схемы API, используя информацию из переменных окружения,
и определяет маршруты для доступа к документации в форматах JSON, YAML, Swagger UI и ReDoc.
"""

from django.urls import re_path

from src.config.settings.swagger import SWAGGER_ENABLED

schema_view = None
urlpatterns = []

if SWAGGER_ENABLED:
    from rest_framework.permissions import AllowAny
    from rest_framework_simplejwt.authentication import JWTAuthentication

    from drf_yasg.views import get_schema_view
    from drf_yasg import openapi

    system_title = 'ERGO MS'

    schema_view = get_schema_view(
        openapi.Info(
            title=f'{system_title} API',
            default_version='v1.0.1',
            description='API эргономичной системы',
            terms_of_service='https://www.google.com/policies/terms/',
        ),
        public=True,
        permission_classes=(AllowAny,),
        authentication_classes=[JWTAuthentication],
    )

    urlpatterns = [
        re_path(
            r'^swagger(?P<format>\.json|\.yaml)$',
            schema_view.without_ui(cache_timeout=0),
            name='schema-json',
        ),
        re_path(
            r'^swagger/$',
            schema_view.with_ui('swagger', cache_timeout=0),
            name='schema-swagger-ui',
        ),
        re_path(
            r'^redoc/$',
            schema_view.with_ui('redoc', cache_timeout=0),
            name='schema-redoc',
        ),
    ]
