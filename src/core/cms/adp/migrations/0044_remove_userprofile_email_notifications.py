from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0043_menuitem_menuseparator_public_id'),
        # Сначала перенос email_notifications -> NotificationPreference.
        ('core_notifications', '0002_preferences_email_delivery'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='email_notifications',
        ),
    ]
