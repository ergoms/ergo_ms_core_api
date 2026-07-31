# -*- coding: utf-8 -*-
"""
Утилиты для миграций меню.

Использование в миграциях:
    from src.core.cms.adp.menu.migration_utils import MenuMigrationHelper

    def populate_menu(apps, schema_editor):
        helper = MenuMigrationHelper(apps, 'modules/<name>')

        # clear удаляет только каталог модуля; layout (order/parent) сохраняется
        # и накатывается на пункты с тем же catalog_key при create_*.
        helper.clear_module_items()

        root = helper.create_group('Мой модуль', 'MyModule', icon='Folder')
        helper.create_route('Главная', 'MyModuleDashboard', parent=root, icon='Home')
"""

from django.db.models import Max

from .catalog_keys import build_item_catalog_key, build_separator_catalog_key


class MenuMigrationHelper:
    """
    Хелпер для создания элементов меню в миграциях.
    Upsert по catalog_key: при повторном seed сохраняет layout из MenuLayoutPlacement.
    """

    ORDER_STEP = 10

    def __init__(self, apps, module_source: str):
        self.apps = apps
        self.MenuItem = apps.get_model('cms_adp', 'MenuItem')
        self.MenuSeparator = apps.get_model('cms_adp', 'MenuSeparator')
        self.module_source = module_source
        self._has_layout_models = self._detect_layout_models(apps)
        if self._has_layout_models:
            self.MenuLayoutPlacement = apps.get_model('cms_adp', 'MenuLayoutPlacement')
            self.MenuSeparatorLayout = apps.get_model('cms_adp', 'MenuSeparatorLayout')

    @staticmethod
    def _detect_layout_models(apps) -> bool:
        try:
            apps.get_model('cms_adp', 'MenuLayoutPlacement')
            apps.get_model('cms_adp', 'MenuSeparatorLayout')
            return True
        except LookupError:
            return False

    def _get_next_order(self, parent=None) -> int:
        max_order = self.MenuItem.objects.filter(
            parent=parent
        ).aggregate(Max('order'))['order__max']
        return (max_order or 0) + self.ORDER_STEP

    def _parent_catalog_key(self, parent) -> str | None:
        if parent is None:
            return None
        return getattr(parent, 'catalog_key', None) or None

    def _item_catalog_key(
        self,
        *,
        item_type: str,
        route_name=None,
        page=None,
        external_url=None,
        name=None,
        parent=None,
    ) -> str:
        return build_item_catalog_key(
            self.module_source,
            item_type=item_type,
            route_name=route_name,
            page=page,
            external_url=external_url,
            name=name,
            parent_catalog_key=self._parent_catalog_key(parent),
        )

    def _get_placement(self, catalog_key: str):
        if not self._has_layout_models or not catalog_key:
            return None
        return self.MenuLayoutPlacement.objects.filter(catalog_key=catalog_key).first()

    def _ensure_item_placement(self, item, *, seed_order, seed_parent, seed_is_active):
        if not self._has_layout_models or not item.catalog_key:
            return
        existing = self.MenuLayoutPlacement.objects.filter(catalog_key=item.catalog_key).first()
        if existing:
            parent = None
            if existing.parent_catalog_key:
                parent = self.MenuItem.objects.filter(
                    catalog_key=existing.parent_catalog_key
                ).first()
            item.parent = parent
            item.order = existing.order
            item.is_active = existing.is_active
            item.save(update_fields=['parent', 'order', 'is_active'])
            return

        parent_key = self._parent_catalog_key(seed_parent)
        self.MenuLayoutPlacement.objects.create(
            catalog_key=item.catalog_key,
            parent_catalog_key=parent_key,
            order=seed_order if seed_order is not None else (item.order or 0),
            is_active=seed_is_active,
        )

    def _ensure_separator_layout(self, sep, *, seed_before_order, seed_before_key, seed_is_active):
        if not self._has_layout_models or not sep.catalog_key:
            return
        existing = self.MenuSeparatorLayout.objects.filter(catalog_key=sep.catalog_key).first()
        if existing:
            sep.before_catalog_key = existing.before_catalog_key
            sep.before_order = existing.before_order
            sep.is_active = existing.is_active
            if existing.name:
                sep.name = existing.name
            sep.save(update_fields=['before_catalog_key', 'before_order', 'is_active', 'name'])
            return

        self.MenuSeparatorLayout.objects.create(
            catalog_key=sep.catalog_key,
            name=sep.name,
            before_catalog_key=seed_before_key,
            before_order=seed_before_order,
            is_active=seed_is_active,
        )

    def clear_module_items(self):
        """
        Удаляет каталог элементов этого модуля.
        Layout (MenuLayoutPlacement) не удаляется — при create_* накатится обратно.
        """
        self.MenuItem.objects.filter(module_source=self.module_source).delete()
        if hasattr(self.MenuSeparator, 'module_source'):
            self.MenuSeparator.objects.filter(module_source=self.module_source).delete()

    def create_item(
        self,
        name: str,
        item_type: str,
        route_name: str = None,
        icon: str = None,
        parent=None,
        page: str = None,
        external_url: str = None,
        is_active: bool = True,
        is_admin_only: bool = False,
        order: int = None,
    ):
        catalog_key = self._item_catalog_key(
            item_type=item_type,
            route_name=route_name,
            page=page,
            external_url=external_url,
            name=name,
            parent=parent,
        )

        existing = (
            self.MenuItem.objects.filter(catalog_key=catalog_key).first()
            if catalog_key
            else None
        )
        placement = self._get_placement(catalog_key)

        if placement is not None:
            parent_obj = None
            if placement.parent_catalog_key:
                parent_obj = self.MenuItem.objects.filter(
                    catalog_key=placement.parent_catalog_key
                ).first()
            effective_parent = parent_obj
            effective_order = placement.order
            effective_active = placement.is_active
        else:
            effective_parent = parent
            effective_order = order if order is not None else self._get_next_order(parent)
            effective_active = is_active

        fields = dict(
            name=name,
            route_name=route_name,
            icon=icon,
            item_type=item_type,
            page=page,
            external_url=external_url,
            parent=effective_parent,
            order=effective_order,
            is_active=effective_active,
            is_admin_only=is_admin_only,
            module_source=self.module_source,
            catalog_key=catalog_key,
        )

        if existing is not None:
            for key, value in fields.items():
                setattr(existing, key, value)
            existing.save()
            item = existing
        else:
            create_kwargs = dict(fields)
            try:
                item = self.MenuItem.objects.create(**create_kwargs)
            except TypeError:
                create_kwargs.pop('catalog_key', None)
                item = self.MenuItem.objects.create(**create_kwargs)
                if hasattr(item, 'catalog_key'):
                    item.catalog_key = catalog_key
                    item.save(update_fields=['catalog_key'])

        self._ensure_item_placement(
            item,
            seed_order=effective_order,
            seed_parent=parent,
            seed_is_active=is_active,
        )
        return item

    def create_route(
        self,
        name: str,
        route_name: str,
        parent=None,
        icon: str = None,
        is_active: bool = True,
        is_admin_only: bool = False,
        order: int = None,
    ):
        return self.create_item(
            name=name,
            item_type='route',
            route_name=route_name,
            icon=icon,
            parent=parent,
            is_active=is_active,
            is_admin_only=is_admin_only,
            order=order,
        )

    def create_group(
        self,
        name: str,
        route_name: str = None,
        parent=None,
        icon: str = None,
        is_active: bool = True,
        is_admin_only: bool = False,
        order: int = None,
    ):
        return self.create_item(
            name=name,
            item_type='route',
            route_name=route_name,
            icon=icon,
            parent=parent,
            is_active=is_active,
            is_admin_only=is_admin_only,
            order=order,
        )

    def create_offcanvas(
        self,
        name: str,
        page: str,
        parent=None,
        icon: str = None,
        is_active: bool = True,
        order: int = None,
    ):
        return self.create_item(
            name=name,
            item_type='offcanvas',
            icon=icon,
            page=page,
            parent=parent,
            is_active=is_active,
            order=order,
        )

    def create_external(
        self,
        name: str,
        url: str,
        parent=None,
        icon: str = None,
        is_active: bool = True,
        order: int = None,
    ):
        return self.create_item(
            name=name,
            item_type='external',
            icon=icon,
            external_url=url,
            parent=parent,
            is_active=is_active,
            order=order,
        )

    def create_separator(
        self,
        name: str,
        before_order: int,
        is_active: bool = True,
        before_catalog_key: str = None,
    ):
        catalog_key = build_separator_catalog_key(self.module_source, name)

        existing = None
        if catalog_key and hasattr(self.MenuSeparator, 'catalog_key'):
            existing = self.MenuSeparator.objects.filter(catalog_key=catalog_key).first()

        create_kwargs = dict(
            name=name,
            before_order=before_order,
            is_active=is_active,
        )
        if hasattr(self.MenuSeparator, 'catalog_key'):
            create_kwargs['catalog_key'] = catalog_key
        if hasattr(self.MenuSeparator, 'module_source'):
            create_kwargs['module_source'] = self.module_source
        if hasattr(self.MenuSeparator, 'before_catalog_key'):
            create_kwargs['before_catalog_key'] = before_catalog_key

        if existing is not None:
            for key, value in create_kwargs.items():
                setattr(existing, key, value)
            existing.save()
            sep = existing
        else:
            sep = self.MenuSeparator.objects.create(**create_kwargs)

        self._ensure_separator_layout(
            sep,
            seed_before_order=before_order,
            seed_before_key=before_catalog_key,
            seed_is_active=is_active,
        )
        return sep

    def create_routes_batch(
        self,
        items: list,
        parent=None,
        is_active: bool = True,
    ):
        created = []
        for item in items:
            if len(item) == 2:
                name, route_name = item
                icon = None
            else:
                name, route_name, icon = item

            created.append(self.create_route(
                name=name,
                route_name=route_name,
                icon=icon,
                parent=parent,
                is_active=is_active,
            ))
        return created

    def create_offcanvas_batch(
        self,
        items: list,
        parent=None,
        is_active: bool = True,
    ):
        created = []
        for item in items:
            if len(item) == 2:
                name, page = item
                icon = None
            else:
                name, page, icon = item

            created.append(self.create_offcanvas(
                name=name,
                page=page,
                icon=icon,
                parent=parent,
                is_active=is_active,
            ))
        return created
