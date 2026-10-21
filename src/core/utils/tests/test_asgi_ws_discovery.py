from pathlib import Path

from django.test import SimpleTestCase


class AsgiWebsocketDiscoveryTests(SimpleTestCase):
    def test_asgi_does_not_hardcode_module_routing(self):
        source = Path(__file__).resolve().parents[3] / 'config' / 'asgi.py'
        text = source.read_text(encoding='utf-8')
        self.assertIn('discover_websocket_urlpatterns', text)
        legacy_pkg = 'src.core.' + 'messen' + 'ger'
        self.assertNotIn(legacy_pkg, text)

    def test_widget_contract_is_not_in_core_catalog(self):
        source = (
            Path(__file__).resolve().parents[2]
            / 'integrations'
            / 'module_contracts.py'
        )
        text = source.read_text(encoding='utf-8')
        self.assertNotIn('chat.room_widget', text)
        source_js = (
            Path(__file__).resolve().parents[5]
            / 'client'
            / 'src'
            / 'integrations'
            / 'moduleContracts.js'
        )
        if source_js.is_file():
            self.assertNotIn('chat.room_widget', source_js.read_text(encoding='utf-8'))
