from django.db import models
from django.conf import settings
from django.utils.translation import gettext_lazy as _

from src.core.settings.services.theme_seed import DEFAULT_THEME_COLORS


class Theme(models.Model):
    """Модель для хранения пользовательских тем"""
    
    class ThemeBase(models.TextChoices):
        LIGHT = 'light', _('Светлая')
        DARK = 'dark', _('Тёмная')
    
    name = models.CharField(_("Название темы"), max_length=100)
    description = models.TextField(_("Описание"), blank=True)
    author = models.CharField(_("Автор"), max_length=100, blank=True)
    base_theme = models.CharField(
        _("Базовая тема"),
        max_length=10,
        choices=ThemeBase.choices,
        default=ThemeBase.LIGHT,
        help_text=_("На какой теме основана (влияет на Bootstrap переменные)")
    )
    is_active = models.BooleanField(_("Активна"), default=False)
    is_default = models.BooleanField(
        _("По умолчанию"),
        default=False,
        help_text=_("Стандарт системы для пользователей без личного выбора"),
    )
    is_available = models.BooleanField(
        _("В быстром выборе"),
        default=False,
        help_text=_("Тема доступна всем в каталоге быстрого выбора"),
    )
    is_system = models.BooleanField(
        _("Системная"),
        default=False,
        help_text=_("Системные темы нельзя удалить")
    )
    
    # Цвета темы - кастомные переменные
    colors = models.JSONField(
        _("Цвета темы"),
        default=dict,
        help_text=_("Кастомные CSS переменные --color-*")
    )
    
    # Bootstrap переменные
    bootstrap_colors = models.JSONField(
        _("Bootstrap цвета"),
        default=dict,
        blank=True,
        help_text=_("Переопределение Bootstrap переменных --bs-*")
    )

    module_key = models.CharField(
        _("Модуль"),
        max_length=100,
        blank=True,
        null=True,
        help_text=_("Ключ модуля (kebab-case). Пусто — глобальная тема системы."),
    )

    module_tokens = models.JSONField(
        _("Токены модуля"),
        default=dict,
        blank=True,
        help_text=_("Дополнительные CSS-переменные модуля (--module-*)"),
    )

    module_pair = models.CharField(
        _("Пара модульной темы"),
        max_length=64,
        blank=True,
        default='',
        help_text=_("Связка light+dark вариантов модуля. Пусто — тема системы."),
    )

    defaults_snapshot = models.JSONField(
        _("Снимок начальных значений"),
        default=dict,
        blank=True,
        help_text=_("Manifest-данные для сброса модульной темы (заполняется при sync-module-defaults)."),
    )
    
    created_at = models.DateTimeField(_("Создана"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлена"), auto_now=True)
    
    class Meta:
        verbose_name = _("Тема")
        verbose_name_plural = _("Темы")
        ordering = ['-is_default', '-is_system', 'name']
        indexes = [
            models.Index(
                fields=['module_key', 'is_active'],
                name='settings_th_module__48e8e9_idx',
            ),
            models.Index(
                fields=['module_key', 'is_default'],
                name='settings_th_module__0d2baf_idx',
            ),
            models.Index(
                fields=['module_key', 'is_available'],
                name='settings_th_module__7988fc_idx',
            ),
        ]

    def __str__(self):
        return self.name
    
    def _scope_filter(self, queryset):
        if self.module_key:
            return queryset.filter(module_key=self.module_key)
        return queryset.filter(module_key__isnull=True)

    def normalized_module_pair(self) -> str:
        if not self.module_key:
            return ''
        return (self.module_pair or 'default').strip() or 'default'

    def save(self, *args, **kwargs):
        if self.module_key:
            self.module_pair = self.normalized_module_pair()

        if self.is_default:
            if self.module_key:
                Theme.objects.filter(module_key=self.module_key).exclude(
                    module_pair=self.normalized_module_pair(),
                ).update(is_default=False)
            else:
                Theme.objects.filter(is_default=True, module_key__isnull=True).exclude(
                    pk=self.pk,
                ).update(is_default=False)

        if self.is_active:
            if self.module_key:
                pair = self.normalized_module_pair()
                Theme.objects.filter(module_key=self.module_key).update(is_active=False)
                super().save(*args, **kwargs)
                Theme.objects.filter(module_key=self.module_key, module_pair=pair).update(
                    is_active=True,
                )
                return
            qs = Theme.objects.filter(is_active=True, module_key__isnull=True)
            qs.exclude(pk=self.pk).update(is_active=False)

        super().save(*args, **kwargs)
    
    @classmethod
    def get_default_colors(cls, base_theme='light'):
        """Возвращает цвета по умолчанию для указанной базовой темы"""
        key = 'dark' if base_theme == 'dark' else 'light'
        return dict(DEFAULT_THEME_COLORS[key])
    
    @classmethod
    def get_default_bootstrap_colors(cls, base_theme='light'):
        """
        Возвращает Bootstrap переменные по умолчанию.
        Значения синхронизированы с _theme.scss
        """
        # Пустой объект - Bootstrap переменные не переопределяются по умолчанию
        # Используются стандартные значения Bootstrap + кастомные из colors
        return {}

class UserThemePreference(models.Model):
    """Личный выбор палитры и быстрый список тем пользователя."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='theme_preference',
        verbose_name=_("Пользователь"),
    )
    selected_theme = models.ForeignKey(
        Theme,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='selected_by_users',
        verbose_name=_("Выбранная тема"),
        help_text=_("Пусто — стандарт системы"),
        limit_choices_to={'module_key__isnull': True},
    )
    favorites = models.ManyToManyField(
        Theme,
        blank=True,
        related_name='favorited_by_users',
        verbose_name=_("Быстрый выбор"),
        limit_choices_to={'module_key__isnull': True},
    )
    updated_at = models.DateTimeField(_("Обновлено"), auto_now=True)

    class Meta:
        verbose_name = _("Предпочтение темы пользователя")
        verbose_name_plural = _("Предпочтения тем пользователей")

    def __str__(self):
        return f"Тема пользователя {self.user_id}"


class EmailSettings(models.Model):
    smtp_host = models.CharField(_("SMTP Host"), max_length=255, blank=True)
    smtp_port = models.PositiveIntegerField(_("SMTP Port"), default=25)
    use_tls = models.BooleanField(_("Use TLS"), default=True)
    username = models.CharField(_("SMTP Username"), max_length=255, blank=True)
    password = models.CharField(_("SMTP Password"), max_length=255, blank=True)
    default_from = models.EmailField(_("Default From Email"), blank=True)

    class Meta:
        verbose_name = _("Email Settings")
        verbose_name_plural = _("Email Settings")

    def __str__(self):
        return _("Email Settings")

class UserAvatar(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='avatar'
    )
    image = models.ImageField(
        upload_to='avatars/',
        blank=True,
        null=True,
        verbose_name='Аватар'
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Аватар для {self.user.username}"
