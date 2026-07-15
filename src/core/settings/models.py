from django.db import models
from django.core.exceptions import ValidationError
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
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
        help_text=_("Использовать как тему по умолчанию")
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
        help_text=_("Ключ модуля (kebab-case). Пусто — глобальная тема сайта."),
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
        help_text=_("Связка light+dark вариантов модуля. Пусто — тема сайта."),
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

class SecuritySettings(models.Model):
    enable_backup = models.BooleanField(
        _("Enable Backup"),
        default=True,
        help_text=_("Показывать кнопку резервного копирования")
    )
    last_backup = models.DateTimeField(
        _("Last Backup Time"),
        null=True,
        blank=True
    )

    class Meta:
        verbose_name = _("Security Settings")
        verbose_name_plural = _("Security Settings")

    def __str__(self):
        return _("Security Settings")


class MediaSettings(models.Model):
    max_upload_size = models.PositiveIntegerField(
        _("Max Upload Size (bytes)"),
        default=5 * 1024 * 1024,
        help_text=_("Максимальный размер загружаемого файла")
    )
    allowed_file_types = models.CharField(
        _("Allowed File Extensions"),
        max_length=255,
        default="jpg,jpeg,png,gif,svg,mp4,mp3,pdf",
        help_text=_("Через запятую, без точек")
    )

    class Meta:
        verbose_name = _("Media Settings")
        verbose_name_plural = _("Media Settings")

    def __str__(self):
        return _("Media Settings")

    def clean(self):
        exts = [e.strip().lower() for e in self.allowed_file_types.split(",")]
        for ext in exts:
            if not ext.isalnum():
                raise ValidationError(
                    _("Недопустимое расширение файла: %(ext)s"), params={"ext": ext}
                )


class PermalinkSettings(models.Model):
    structure = models.CharField(
        _("URL Structure"),
        max_length=255,
        default="/%year%/%month%/%slug%/",
        help_text=_("Например: /%year%/%month%/%slug%/")
    )

    class Meta:
        verbose_name = _("Permalink Settings")
        verbose_name_plural = _("Permalink Settings")

    def __str__(self):
        return _("Permalink Settings")


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

class AuditLog(models.Model):
    ACTIONS = (
        ('UPDATE', 'Обновление'),
        ('DELETE', 'Удаление'),
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id    = models.PositiveIntegerField()
    action       = models.CharField(max_length=6, choices=ACTIONS)
    changes      = models.JSONField(null=True, blank=True)
    user         = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    timestamp    = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Запись аудита"
        verbose_name_plural = "Аудит-журналы"
        indexes = [
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.get_action_display()} #{self.object_id} by {self.user}"
