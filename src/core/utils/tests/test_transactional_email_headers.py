"""Заголовки transactional-писем (Message-ID, Auto-Submitted, List-Unsubscribe)."""

from __future__ import annotations

from django.core.mail import EmailMultiAlternatives
from django.test import SimpleTestCase, override_settings

from src.core.utils.transactional_email_headers import (
    apply_transactional_email_headers,
    message_id_domain,
    relabel_from_display_name,
)


class MessageIdDomainTests(SimpleTestCase):
    def test_from_email_domain(self):
        self.assertEqual(
            message_id_domain('ERGOMS <info@app.example.test>'),
            'app.example.test',
        )

    @override_settings(FRONTEND_BASE_URL='https://app.example.test')
    def test_fallback_frontend_host(self):
        self.assertEqual(message_id_domain(''), 'app.example.test')


class ApplyTransactionalHeadersTests(SimpleTestCase):
    def test_headers_and_reply_to(self):
        message = EmailMultiAlternatives(
            subject='Тема',
            body='Текст',
            from_email='ERGOMS <info@app.example.test>',
            to=['user@example.com'],
        )
        apply_transactional_email_headers(
            message,
            from_email='ERGOMS <info@app.example.test>',
            unsubscribe_url='https://app.example.test/user/notifications',
        )
        self.assertEqual(message.reply_to, ['info@app.example.test'])
        self.assertIn('Message-ID', message.extra_headers)
        self.assertTrue(str(message.extra_headers['Message-ID']).endswith('@app.example.test>'))
        self.assertEqual(message.extra_headers['Auto-Submitted'], 'auto-generated')
        self.assertEqual(
            message.extra_headers['List-Unsubscribe'],
            '<https://app.example.test/user/notifications>',
        )
        self.assertEqual(
            message.extra_headers['List-Unsubscribe-Post'],
            'List-Unsubscribe=One-Click',
        )
        self.assertIn('Date', message.extra_headers)

    def test_relabel_keeps_address(self):
        self.assertEqual(
            relabel_from_display_name('ERGOMS <info@app.example.test>', 'Acme'),
            'Acme <info@app.example.test>',
        )
        self.assertEqual(
            relabel_from_display_name('info@app.example.test', 'Acme'),
            'Acme <info@app.example.test>',
        )
        self.assertEqual(relabel_from_display_name('info@app.example.test', ''), 'info@app.example.test')

    def test_without_unsubscribe(self):
        message = EmailMultiAlternatives(
            subject='Тема',
            body='Текст',
            from_email='info@app.example.test',
            to=['user@example.com'],
        )
        apply_transactional_email_headers(message, from_email='info@app.example.test')
        self.assertNotIn('List-Unsubscribe', message.extra_headers)
        self.assertNotIn('List-Unsubscribe-Post', message.extra_headers)
        self.assertEqual(message.extra_headers['Auto-Submitted'], 'auto-generated')
