"""Пункты меню вынесенного модуля не прячутся из-за DISABLED_MODULES."""

from unittest.mock import patch

from django.test import SimpleTestCase

from src.core.utils.module_registry import is_menu_module_hidden


class MenuModuleHiddenTests(SimpleTestCase):
    def test_disabled_without_process_is_hidden(self):
        with (
            patch('src.core.utils.module_registry.is_module_disabled', return_value=True),
            patch('src.core.utils.module_registry.is_externally_served_module', return_value=False),
        ):
            self.assertTrue(is_menu_module_hidden('demo'))

    def test_disabled_remote_stays_visible(self):
        with (
            patch('src.core.utils.module_registry.is_module_disabled', return_value=True),
            patch('src.core.utils.module_registry.is_externally_served_module', return_value=True),
        ):
            self.assertFalse(is_menu_module_hidden('demo'))

    def test_loaded_module_is_visible(self):
        with patch('src.core.utils.module_registry.is_module_disabled', return_value=False):
            self.assertFalse(is_menu_module_hidden('demo'))

    def test_empty_name_is_visible(self):
        self.assertFalse(is_menu_module_hidden(None))
        self.assertFalse(is_menu_module_hidden(''))
