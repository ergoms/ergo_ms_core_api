"""
Настройки доступа к документации API (Swagger UI / ReDoc) из переменных окружения (.env).
"""

from src.config.env import env

_deploy_type = env.str('API_DEPLOY_TYPE', default='production').strip().lower()
_default_swagger_enabled = _deploy_type != 'production'

SWAGGER_ENABLED = env.bool('API_SWAGGER_ENABLED', default=_default_swagger_enabled)

SWAGGER_SETTINGS = {
    'DEFAULT_FIELD_INSPECTORS': [
        'drf_yasg.inspectors.CamelCaseJSONFilter',
        'drf_yasg.inspectors.RecursiveFieldInspector',
        'src.core.utils.swagger.inspectors.UniqueRefNameSerializerInspector',
        'drf_yasg.inspectors.ChoiceFieldInspector',
        'drf_yasg.inspectors.FileFieldInspector',
        'drf_yasg.inspectors.DictFieldInspector',
        'drf_yasg.inspectors.JSONFieldInspector',
        'drf_yasg.inspectors.HiddenFieldInspector',
        'drf_yasg.inspectors.RelatedFieldInspector',
        'drf_yasg.inspectors.SerializerMethodFieldInspector',
        'drf_yasg.inspectors.SimpleFieldInspector',
        'drf_yasg.inspectors.StringDefaultFieldInspector',
    ],
}
