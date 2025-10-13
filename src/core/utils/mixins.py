class SwaggerSafeMixin:
    """
    Миксин для безопасной работы с Swagger генерацией схемы.
    Предотвращает ошибки при генерации документации API.
    """
    
    def is_swagger_fake_view(self):
        """Проверяет, является ли текущий запрос фейковым для Swagger"""
        return getattr(self, 'swagger_fake_view', False)
    
    def get_safe_user(self):
        """Безопасно получает пользователя, учитывая Swagger контекст"""
        if self.is_swagger_fake_view():
            return None
        return self.request.user
    
    def get_safe_queryset(self, base_queryset):
        """Безопасно фильтрует queryset, учитывая Swagger контекст"""
        if self.is_swagger_fake_view():
            return base_queryset.none()
        return base_queryset 