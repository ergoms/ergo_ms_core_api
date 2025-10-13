from django.db import migrations
from django.utils import timezone

def create_default_settings(apps, schema_editor):
    GeneralSettings = apps.get_model('settings', 'GeneralSettings')
    AppearanceSettings = apps.get_model('settings', 'AppearanceSettings')
    SecuritySettings = apps.get_model('settings', 'SecuritySettings')
    MediaSettings = apps.get_model('settings', 'MediaSettings')
    PermalinkSettings = apps.get_model('settings', 'PermalinkSettings')
    EmailSettings = apps.get_model('settings', 'EmailSettings')

    # Создаем основные настройки сайта
    GeneralSettings.objects.create(
        site_name="ERGO MS",
        site_tagline="Система управления организациями",
        site_url="http://localhost:8000",
        admin_email="admin@example.com",
        homepage_type="latest",
        posts_per_page=10,
        discourage_search_engines=True,
        privacy_policy="Политика конфиденциальности будет добавлена позже."
    )

    # Настройки внешнего вида
    AppearanceSettings.objects.create(
        theme_name="default",
        config={
            "primary_color": "#007bff",
            "secondary_color": "#6c757d"
        }
    )

    # Настройки безопасности
    SecuritySettings.objects.create(
        enable_backup=True,
        last_backup=None
    )

    # Настройки медиа
    MediaSettings.objects.create(
        max_upload_size=5 * 1024 * 1024,  # 5MB
        allowed_file_types="jpg,jpeg,png,gif,svg,mp4,mp3,pdf"
    )

    # Настройки постоянных ссылок
    PermalinkSettings.objects.create(
        structure="/%year%/%month%/%slug%/"
    )

    # Настройки email
    EmailSettings.objects.create(
        smtp_host="smtp.example.com",
        smtp_port=587,
        use_tls=True,
        username="",
        password="",
        default_from="noreply@example.com"
    )

class Migration(migrations.Migration):

    dependencies = [
        ('settings', '0008_auditlog'),
    ]

    operations = [
        migrations.RunPython(create_default_settings),
    ] 