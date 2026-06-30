from django.db import migrations
from django.utils import timezone

def create_default_settings(apps, schema_editor):
    SecuritySettings = apps.get_model('settings', 'SecuritySettings')
    MediaSettings = apps.get_model('settings', 'MediaSettings')
    PermalinkSettings = apps.get_model('settings', 'PermalinkSettings')
    EmailSettings = apps.get_model('settings', 'EmailSettings')

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