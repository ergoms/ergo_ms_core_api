"""Нормализация непрозрачного scope_ref уведомления."""

from unittest.mock import patch
from uuid import uuid4

from django.test import SimpleTestCase

from src.core.notifications.scope import (
    normalize_scope_label,
    normalize_scope_ref,
    resolve_scope_labels,
)


class NormalizeScopeRefTests(SimpleTestCase):
    def test_normalize_blank(self):
        self.assertEqual(normalize_scope_ref('  '), '')
        self.assertEqual(normalize_scope_ref(None), '')

    def test_normalize_keeps_public_id(self):
        ref = str(uuid4())
        self.assertEqual(normalize_scope_ref(ref), ref)

    def test_normalize_label_collapses_spaces(self):
        self.assertEqual(normalize_scope_label('  ООО   «Ромашка»  '), 'ООО «Ромашка»')
        self.assertEqual(normalize_scope_label(None), '')

    def test_resolve_labels_skips_empty_and_normalizes(self):
        ref = str(uuid4())
        with patch('src.core.notifications.scope.bridge.call', return_value={ref: '  Имя  '}) as call:
            labels = resolve_scope_labels(['', ref, ref])
        call.assert_called_once()
        self.assertEqual(labels, {ref: 'Имя'})

    def test_resolve_labels_empty_without_bridge(self):
        self.assertEqual(resolve_scope_labels([]), {})
        self.assertEqual(resolve_scope_labels(None), {})
