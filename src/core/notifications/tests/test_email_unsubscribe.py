"""GET не гасит канал, POST гасит; неверный токен даёт нейтральный 200."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from src.core.notifications.email_unsubscribe import (
    build_unsubscribe_url,
    sign_unsubscribe_token,
)
from src.core.notifications.models import NotificationPreference
from src.core.notifications.preferences import GLOBAL_KEY


class NotificationEmailUnsubscribeTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username='notif-unsub-user',
            email='staff@example.test',
        )
        self.token = sign_unsubscribe_token(user_public_id=str(self.user.public_id))

    def _url(self):
        try:
            return reverse('notification-email-unsubscribe')
        except Exception:
            return '/notifications/email/unsubscribe/'

    def test_get_does_not_disable_email(self):
        client = Client()
        response = client.get(self._url(), {'token': self.token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Отписаться от писем')
        self.assertFalse(
            NotificationPreference.objects.filter(
                user=self.user,
                source_module=GLOBAL_KEY,
                event_key=GLOBAL_KEY,
                channel='email',
            ).exists(),
        )

    def test_post_disables_email_channel(self):
        client = Client()
        response = client.post(self._url(), {'token': self.token})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Вы отписались')
        row = NotificationPreference.objects.get(
            user=self.user,
            source_module=GLOBAL_KEY,
            event_key=GLOBAL_KEY,
            channel='email',
        )
        self.assertFalse(row.enabled)

    def test_one_click_post_disables_email(self):
        client = Client()
        response = client.post(
            f'{self._url()}?token={self.token}',
            data='List-Unsubscribe=One-Click',
            content_type='application/x-www-form-urlencoded',
        )
        self.assertEqual(response.status_code, 200)
        row = NotificationPreference.objects.get(
            user=self.user,
            source_module=GLOBAL_KEY,
            event_key=GLOBAL_KEY,
            channel='email',
        )
        self.assertFalse(row.enabled)

    def test_invalid_token_is_neutral(self):
        client = Client()
        response = client.post(self._url(), {'token': 'not-a-token'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            NotificationPreference.objects.filter(
                user=self.user,
                channel='email',
            ).exists(),
        )


@override_settings(FRONTEND_BASE_URL='https://app.example.test')
class NotificationUnsubscribeUrlTests(TestCase):
    def test_empty_origin_omits_url(self):
        with self.settings(FRONTEND_BASE_URL=''):
            from unittest.mock import patch

            with patch(
                'src.core.notifications.email_unsubscribe.notification_public_origin',
                return_value='',
            ):
                self.assertEqual(build_unsubscribe_url(user_public_id='abc'), '')

    def test_builds_tokenized_url(self):
        from unittest.mock import patch

        with patch(
            'src.core.notifications.email_unsubscribe.notification_public_origin',
            return_value='https://app.example.test',
        ):
            url = build_unsubscribe_url(user_public_id='aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.assertTrue(url.startswith(
            'https://app.example.test/api/notifications/email/unsubscribe/?token=',
        ))
        self.assertNotIn('pk=', url)
        self.assertNotIn('user_id=', url)
