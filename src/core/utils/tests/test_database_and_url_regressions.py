from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, TestCase
from django.urls import include, path, reverse
from sqlalchemy import literal, select

from src.core.utils.auto_api.discovered_urls_cache import _url_fingerprint
from src.core.utils.database.main import DjangoSAExecutor


class UrlDiscoveryRegressionTests(SimpleTestCase):
    def test_including_api_urls_does_not_add_an_implicit_namespace(self):
        urls = (path('api/', include('src.config.urls')),)
        self.assertEqual(reverse('jupyter-access', urlconf=urls), '/api/internal/jupyter-access/')

    def test_discovery_cache_separates_installed_app_sets(self):
        with patch.object(settings, 'INSTALLED_APPS', ['django.contrib.auth']):
            first = _url_fingerprint()
        with patch.object(settings, 'INSTALLED_APPS', ['django.contrib.auth', 'django.contrib.contenttypes']):
            second = _url_fingerprint()
        self.assertNotEqual(first['installed_apps'], second['installed_apps'])


class DatabaseLiteralRegressionTests(TestCase):
    def test_literal_and_parameterized_queries_return_the_same_percent_and_quote(self):
        statement = select(literal("100% готово, O'Brien"))
        for literal_binds in (True, False):
            with self.subTest(literal_binds=literal_binds):
                row = DjangoSAExecutor.fetchone(statement, literal_binds=literal_binds)
                self.assertEqual(row[0], "100% готово, O'Brien")
