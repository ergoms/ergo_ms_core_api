"""Exercise real CORS preflights using the API header configuration, without a database."""
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from corsheaders.defaults import default_headers
from corsheaders.middleware import CorsMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, override_settings


class CorsIdempotencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from django.conf import settings
        super().setUpClass()
        if not settings.configured:
            settings.configure(SECRET_KEY='isolated-cors-regression', DEFAULT_CHARSET='utf-8')
        values = {'CORS_ALLOWED_ORIGINS': 'https://client.example'}
        stubs = {
            'src.config.deploy': SimpleNamespace(is_development=lambda: False),
            'src.config.env': SimpleNamespace(env=SimpleNamespace(
                str=lambda key, default='': values.get(key, default))),
            'src.config.nginx_runtime': SimpleNamespace(effective_cors_origins=lambda origins: origins),
        }
        with patch.dict(sys.modules, stubs):
            configured = runpy.run_path(str(Path(__file__).resolve().parents[1]
                                              / 'src/config/settings/cors.py'))
        cls.cors = {key: value for key, value in configured.items() if key.startswith('CORS_')}

    def preflight(self, method='PUT', origin='https://client.example', headers=None):
        request = RequestFactory().options(
            '/api/scout/runs/example/retention/hold/', HTTP_ORIGIN=origin,
            HTTP_ACCESS_CONTROL_REQUEST_METHOD=method,
            HTTP_ACCESS_CONTROL_REQUEST_HEADERS=headers or 'authorization,content-type,idempotency-key',
        )
        with override_settings(**self.cors):
            return CorsMiddleware(lambda request: HttpResponse(status=204))(request)

    def test_put_and_delete_allow_idempotency_with_existing_auth_headers(self):
        for method in ('PUT', 'DELETE'):
            with self.subTest(method=method):
                response = self.preflight(method)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Access-Control-Allow-Origin'], 'https://client.example')
                self.assertEqual(response['Access-Control-Allow-Credentials'], 'true')
                allowed = {name.strip().lower() for name in response['Access-Control-Allow-Headers'].split(',')}
                self.assertTrue(set(default_headers).issubset(allowed))
                self.assertTrue({'authorization', 'content-type', 'idempotency-key'}.issubset(allowed))
                self.assertIn(method, response['Access-Control-Allow-Methods'])

    def test_untrusted_origin_is_not_granted_access(self):
        self.assertNotIn('Access-Control-Allow-Origin', self.preflight(origin='https://untrusted.example'))

    def test_allowlist_does_not_allow_arbitrary_headers_or_wildcards(self):
        response = self.preflight(headers='authorization,x-not-allowed')
        allowed = {name.strip().lower() for name in response['Access-Control-Allow-Headers'].split(',')}
        self.assertNotIn('x-not-allowed', allowed)
        self.assertNotIn('*', allowed)
        self.assertFalse(self.cors['CORS_ALLOW_ALL_ORIGINS'])


if __name__ == '__main__':
    unittest.main()
