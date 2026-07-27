"""
Активирует язык из UserProfile для аутентифицированных запросов.

LocaleMiddleware уже разобрал Accept-Language / cookie.
Если у пользователя задан language в профиле — он имеет приоритет.
"""

from django.conf import settings
from django.utils import translation


class ProfileLocaleMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self._supported = frozenset(
            getattr(settings, 'SUPPORTED_UI_LANGUAGES', None)
            or {code for code, _ in getattr(settings, 'LANGUAGES', ())}
        )

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and getattr(user, 'is_authenticated', False):
            language = self._profile_language(user)
            if language:
                translation.activate(language)
                request.LANGUAGE_CODE = language

        response = self.get_response(request)
        return response

    def _profile_language(self, user):
        profile = getattr(user, 'adp_profile', None)
        if profile is None:
            try:
                from src.core.cms.adp.models import UserProfile

                profile = UserProfile.objects.filter(user_id=user.pk).only('language').first()
            except Exception:
                return None
        language = getattr(profile, 'language', None) if profile is not None else None
        if not language or not isinstance(language, str):
            return None
        code = language.strip().lower().split('-', 1)[0]
        if code in self._supported:
            return code
        return None
