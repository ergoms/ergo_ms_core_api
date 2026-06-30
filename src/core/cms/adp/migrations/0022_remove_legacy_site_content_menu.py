# -*- coding: utf-8 -*-

from django.db import migrations


REMOVED_ROUTE_NAMES = (
    'SiteSettings',
    'Shortcodes',
    'MainShortcodePage',
    'Templates',
    'Pages',
    'Layouts',
    'PageShortcodeCategories',
    'Categories',
    'PageCategories',
    'PageCategoriesManager',
    'TagsManager',
)

REMOVED_MODULE_SOURCES = (
    'core/shortcodes',
    'cms_shortcodes',
    'core/categories',
)


def remove_legacy_site_content_menu(apps, schema_editor):
    MenuItem = apps.get_model('cms_adp', 'MenuItem')
    MenuItem.objects.filter(module_source__in=REMOVED_MODULE_SOURCES).delete()
    MenuItem.objects.filter(route_name__in=REMOVED_ROUTE_NAMES).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('cms_adp', '0021_userpresence'),
    ]

    operations = [
        migrations.RunPython(
            remove_legacy_site_content_menu,
            migrations.RunPython.noop,
        ),
    ]
