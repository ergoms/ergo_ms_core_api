from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0043_menuitem_menuseparator_public_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='userprofile',
            name='email_notifications',
        ),
    ]
