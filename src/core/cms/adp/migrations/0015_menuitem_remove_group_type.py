from django.db import migrations


def group_to_route(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(item_type='group').update(item_type='route')


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0014_remove_filemanager_menu'),
    ]

    operations = [
        migrations.RunPython(group_to_route, noop),
    ]
