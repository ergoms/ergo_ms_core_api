"""MailService ставит transactional-заголовки и не шлёт pk в ссылке."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from django.core import mail
from django.test import SimpleTestCase, override_settings

from src.core.notifications.email_templates import RelatedEmailImage, RenderedEmail
from src.core.notifications.mail_service import MailService

_MINIMAL_PNG = bytes.fromhex(
    '89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de'
    '0000000c49444154789c63f8cfc0000003010100c9fe92ef0000000049454e44ae426082'
)


@override_settings(
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
    FRONTEND_BASE_URL='https://app.example.test',
)
class MailServiceHeadersTests(SimpleTestCase):
    def test_sends_with_unsubscribe_and_auto_submitted(self):
        rendered = RenderedEmail(
            subject='Срок задачи через час',
            html_body='<p>ok</p>',
            text_body='ok',
            from_email=None,
        )
        notification = SimpleNamespace(
            pk=38,
            route={'name': 'ItemDetail'},
            recipient=SimpleNamespace(public_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'),
        )
        connection = mail.get_connection()
        with (
            patch('src.core.notifications.mail_service.is_email_enabled', return_value=True),
            patch(
                'src.core.notifications.mail_service.resolve_connection_and_from',
                return_value=(connection, 'ERGOMS <info@app.example.test>'),
            ),
            patch(
                'src.core.notifications.mail_service.EmailTemplateResolver.resolve',
                return_value=rendered,
            ),
            patch('src.core.notifications.mail_service.apply_django_smtp_helo_override'),
            patch(
                'src.core.notifications.mail_service.resolve_unsubscribe_url',
                return_value='https://app.example.test/api/notifications/email/unsubscribe/?token=abc',
            ),
        ):
            result = MailService.send_notification_email(
                notification=notification,
                recipient_email='user@example.com',
            )
        self.assertTrue(result.success)
        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.extra_headers.get('Auto-Submitted'), 'auto-generated')
        self.assertEqual(
            sent.extra_headers.get('List-Unsubscribe'),
            '<https://app.example.test/api/notifications/email/unsubscribe/?token=abc>',
        )
        self.assertEqual(
            sent.extra_headers.get('List-Unsubscribe-Post'),
            'List-Unsubscribe=One-Click',
        )
        self.assertIn('Message-ID', sent.extra_headers)
        self.assertNotIn('open=38', sent.body)
        self.assertNotIn('open=38', sent.alternatives[0][0] if sent.alternatives else '')

    def test_attaches_related_image_as_cid(self):
        rendered = RenderedEmail(
            subject='Вам задача: тест',
            html_body='<img src="cid:company-logo">',
            text_body='ok',
            from_email=None,
            related_images=(
                RelatedEmailImage(
                    cid='company-logo',
                    content=_MINIMAL_PNG,
                    subtype='png',
                    filename='company-logo.png',
                ),
            ),
        )
        notification = SimpleNamespace(
            pk=38,
            route={'name': 'ItemDetail'},
            recipient=SimpleNamespace(public_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'),
        )
        connection = mail.get_connection()
        mail.outbox.clear()
        with (
            patch('src.core.notifications.mail_service.is_email_enabled', return_value=True),
            patch(
                'src.core.notifications.mail_service.resolve_connection_and_from',
                return_value=(connection, 'Acme <info@example.test>'),
            ),
            patch(
                'src.core.notifications.mail_service.EmailTemplateResolver.resolve',
                return_value=rendered,
            ),
            patch('src.core.notifications.mail_service.apply_django_smtp_helo_override'),
            patch(
                'src.core.notifications.mail_service.resolve_unsubscribe_url',
                return_value='',
            ),
        ):
            result = MailService.send_notification_email(
                notification=notification,
                recipient_email='user@example.com',
            )
        self.assertTrue(result.success)
        sent = mail.outbox[0]
        self.assertEqual(sent.mixed_subtype, 'related')
        mime = sent.message()
        cids = [str(part.get('Content-ID') or '') for part in mime.walk()]
        self.assertIn('<company-logo>', cids)
