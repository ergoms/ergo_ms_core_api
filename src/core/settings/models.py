from django.db import models
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group, Permission
from django.core.validators import FileExtensionValidator
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from slugify import slugify
from django.utils.translation import gettext_lazy as _

class GeneralSettings(models.Model):
    site_name = models.CharField(_("Название сайта"), max_length=255, default="My Site")
    site_tagline = models.CharField(_("Tagline"), max_length=255, blank=True)
    site_url = models.URLField(_("URL сайта"), max_length=200)
    admin_email = models.EmailField(_("Email администратора"), max_length=254)
    roles = models.ManyToManyField(
    Group,
    verbose_name=_("Роли пользователей"),
    blank=True,
    help_text=_("Группы пользователей, доступных в системе")
)
    # Настройки главной страницы
    class HomePageChoices(models.TextChoices):
        STATIC = "static", _("Статическая страница")
        LATEST = "latest", _("Последние сообщения")
    homepage_type = models.CharField(
        _("Тип домашней страницы"),
        max_length=10,
        choices=HomePageChoices.choices,
        default=HomePageChoices.LATEST
    )
    posts_per_page = models.PositiveIntegerField(_("Посты на страницу"), default=10)
    discourage_search_engines = models.BooleanField(
        _("Discourage Search Engines"),
        default=False,
        help_text=_("Запретить индексацию сайта")
    )
    privacy_policy = models.TextField(_("Политика конфиденциальности"), blank=True)

    class Meta:
        verbose_name = _("Общие настройки")
        verbose_name_plural = _("Общие настройки")

    def __str__(self):
        return _("Общие настройки")


class AppearanceSettings(models.Model):
    # Хранит настройки темы
    theme_name = models.CharField(_("Название темы"), max_length=100, default="default")
    # Дополнительные JSON-настройки, например, цветовые схемы
    config = models.JSONField(_("Конфигурация темы"), default=dict, blank=True)
    # Полная конфигурация темы (light и dark)
    theme_config = models.JSONField(
        _("Полная конфигурация темы"),
        default=dict,
        blank=True,
        help_text=_("JSON с настройками цветов для light и dark тем")
    )

    class Meta:
        verbose_name = _("Настройки внешнего вида")
        verbose_name_plural = _("Настройки внешнего вида")

    def __str__(self):
        return f"{self.theme_name}"


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
    
    created_at = models.DateTimeField(_("Создана"), auto_now_add=True)
    updated_at = models.DateTimeField(_("Обновлена"), auto_now=True)
    
    class Meta:
        verbose_name = _("Тема")
        verbose_name_plural = _("Темы")
        ordering = ['-is_default', '-is_system', 'name']
    
    def __str__(self):
        return self.name
    
    def save(self, *args, **kwargs):
        # Если устанавливаем тему по умолчанию, снимаем флаг с других
        if self.is_default:
            Theme.objects.filter(is_default=True).exclude(pk=self.pk).update(is_default=False)
        # Если устанавливаем активную тему, снимаем флаг с других
        if self.is_active:
            Theme.objects.filter(is_active=True).exclude(pk=self.pk).update(is_active=False)
        super().save(*args, **kwargs)
    
    @classmethod
    def get_default_colors(cls, base_theme='light'):
        """Возвращает цвета по умолчанию для указанной базовой темы"""
        if base_theme == 'dark':
            return {
                'headerBackground': 'rgba(30, 30, 30, 0.85)',
                'authBackground': 'rgba(30, 30, 30, 0.7)',
                'background': '#111112',
                'border': '#555555',
                'primaryText': '#c9cccf',
                'secondaryText': '#6e6e6e',
                'primaryBackground': '#18181a',
                'secondaryBackground': '#2a2a2c',
                'hoverBackground': '#3d3d3f',
                'accent': '#f14336'
            }
        return {
            'headerBackground': 'rgba(255, 255, 255, 0.85)',
            'authBackground': 'rgba(255, 255, 255, 0.7)',
            'background': '#f2f2f2',
            'border': '#e0e0e0',
            'primaryText': '#101223',
            'secondaryText': '#6e6e6e',
            'primaryBackground': '#ffffff',
            'secondaryBackground': '#f1f1f1',
            'hoverBackground': '#e1e1e1',
            'accent': '#d0322d'
        }
    
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
class UploadedFile(models.Model):
    file = models.FileField(upload_to='uploads/')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    alt_name = models.CharField(
        "Альтернативное название",
        max_length=255,
        blank=True,
        help_text="Понятное пользователю название файла"
    )

    def __str__(self):
        return self.alt_name or self.file.name
class Category(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название категории")
    slug = models.SlugField(max_length=255, verbose_name="Slug", blank=True)
    parent = models.ForeignKey(
        'self', null=True, blank=True,
        on_delete=models.CASCADE,
        related_name='children',
        verbose_name="Родительская категория"
    )

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        unique_together = [['parent', 'slug']]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            n = 1
            while Category.objects.filter(parent=self.parent, slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{n}"
                n += 1
            self.slug = slug
        super().save(*args, **kwargs)

class Tag(models.Model):
    name = models.CharField("Название тега", max_length=255, unique=True)
    category = models.ForeignKey(
        Category, on_delete=models.CASCADE, related_name="tags", verbose_name="Категория", null=True, blank=True
    )

    class Meta:
        verbose_name = "Тег"
        verbose_name_plural = "Теги"

    def __str__(self):
        return self.name
    
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
