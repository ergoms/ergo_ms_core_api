from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from src.core.cms.adp.models import PresenceConnection, SessionConnectionInterval, UserDevice
from src.core.cms.adp.services import connection_history as service
from src.core.cms.adp.services.session_devices import revoke_user_device_session
from src.core.cms.adp.services.user_deletion import revoke_user_auth
from src.core.cms.adp.views_presence import UserPresenceHeartbeatView, UserPresenceOfflineView
from src.core.realtime.sync_view import RealtimeSyncView


class ConnectionHistoryTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='connection-user')
        self.other = get_user_model().objects.create_user(username='connection-other')
        self.device = UserDevice.objects.create(
            user=self.user, device_name='Chrome · Windows', device_type='desktop',
            user_agent='Mozilla Windows Chrome/123', ip_address='192.0.2.10', is_active=True,
        )
        self.now = timezone.now()
        self.clock = patch.object(service.timezone, 'now', return_value=self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        dimensions = patch.object(service.bridge, 'emit', side_effect=lambda event, **kwargs: [
            {'tenant': kwargs['claims'].get('tenant')},
        ])
        dimensions.start()
        self.addCleanup(dimensions.stop)
        self.request = SimpleNamespace(user=self.user, auth={'device_id': self.device.pk, 'tenant': 1},
                                       META={'REMOTE_ADDR': '192.0.2.10', 'HTTP_USER_AGENT': self.device.user_agent})
        self.tab = uuid4()

    def beat(self, tab=None, *, offset=0, request=None):
        service.heartbeat(request or self.request, tab or self.tab, now=self.now + timedelta(seconds=offset))

    def snapshot(self, tenant=1, offset=0):
        return service.summary(scope={'tenant': tenant}, actor_refs=[str(self.user.public_id)],
                               now=self.now + timedelta(seconds=offset))['employees'][0]

    def test_tabs_share_interval_and_one_close_keeps_other_online(self):
        second = uuid4()
        self.beat()
        self.beat(second, offset=2)
        service.disconnect(self.request, self.tab, terminal=True, now=self.now + timedelta(seconds=3))
        self.assertEqual(SessionConnectionInterval.objects.count(), 1)
        self.assertTrue(self.snapshot(offset=4)['is_online'])
        service.disconnect(self.request, second, terminal=True, now=self.now + timedelta(seconds=5))
        self.assertFalse(self.snapshot(offset=5)['is_online'])
        interval = SessionConnectionInterval.objects.get()
        self.assertEqual(interval.end_reason, 'disconnect')
        self.assertEqual(interval.ended_at, self.now + timedelta(seconds=5))

    def test_reconnect_within_threshold_continues_interval(self):
        self.beat()
        service.disconnect(self.request, self.tab, now=self.now + timedelta(seconds=3))
        self.beat(offset=20)
        self.assertEqual(SessionConnectionInterval.objects.count(), 1)
        self.assertTrue(self.snapshot(offset=20)['is_online'])

    def test_exact_timeout_boundary_and_lost_connection_has_no_invented_end(self):
        self.beat()
        threshold = service.get_presence_stale_threshold_seconds()
        self.assertTrue(self.snapshot(offset=threshold - 0.001)['is_online'])
        self.assertFalse(self.snapshot(offset=threshold)['is_online'])
        service.maintain_history(now=self.now + timedelta(seconds=threshold))
        interval = SessionConnectionInterval.objects.get()
        self.assertEqual(interval.end_reason, 'timeout')
        self.assertIsNone(interval.ended_at)
        self.beat(offset=threshold + 1)
        self.assertEqual(SessionConnectionInterval.objects.count(), 2)

    def test_company_change_closes_only_current_tab_and_late_request_cannot_restore(self):
        self.beat()
        second = uuid4()
        self.beat(second)
        service.disconnect(self.request, self.tab, reason='scope_changed', now=self.now)
        self.beat(offset=2)
        self.assertEqual(PresenceConnection.objects.filter(connection_id=self.tab, is_active=True).count(), 0)
        self.assertTrue(self.snapshot()['is_online'])
        next_request = SimpleNamespace(user=self.user, auth={**self.request.auth, 'tenant': 2}, META=self.request.META)
        self.beat(uuid4(), request=next_request)
        self.assertTrue(self.snapshot(tenant=2)['is_online'])
        self.assertEqual(SessionConnectionInterval.objects.count(), 2)

    def test_close_before_first_heartbeat_leaves_no_fake_history(self):
        service.disconnect(self.request, self.tab, reason='scope_changed')
        self.beat()
        self.assertEqual(SessionConnectionInterval.objects.count(), 0)
        self.assertEqual(PresenceConnection.objects.count(), 1)

    def test_ownership_cannot_be_forged_by_connection_id(self):
        self.beat()
        forged = SimpleNamespace(user=self.other, auth=self.request.auth, META=self.request.META)
        service.disconnect(forged, self.tab, reason='logout')
        self.assertTrue(self.snapshot()['is_online'])
        self.beat(request=forged)
        self.assertEqual(SessionConnectionInterval.objects.count(), 1)

    def test_revocation_preserves_snapshot_and_ends_connection(self):
        self.beat()
        public_id = SessionConnectionInterval.objects.get().public_id
        revoke_user_device_session(self.device)
        interval = SessionConnectionInterval.objects.get(public_id=public_id)
        self.assertEqual(interval.end_reason, 'revoked')
        self.assertEqual(interval.ip_address, '192.0.2.10')
        self.assertFalse(self.snapshot()['is_online'])
        self.beat(offset=1)
        self.assertEqual(SessionConnectionInterval.objects.count(), 1)

    def test_revoke_all_respects_kept_device(self):
        self.beat()
        other_device = UserDevice.objects.create(user=self.user, device_name='Phone', device_type='mobile',
                                                user_agent='Android Chrome/123', ip_address='192.0.2.11', is_active=True)
        other_request = SimpleNamespace(user=self.user, auth={**self.request.auth, 'device_id': other_device.pk}, META=self.request.META)
        self.beat(uuid4(), request=other_request)
        revoke_user_auth(self.user, except_device_id=self.device.pk)
        self.assertTrue(self.snapshot()['is_online'])
        self.assertEqual(SessionConnectionInterval.objects.filter(end_reason='revoked').count(), 1)

    def test_late_close_for_deleted_or_foreign_device_is_ignored(self):
        foreign_request = SimpleNamespace(user=self.other, auth=self.request.auth, META=self.request.META)
        service.disconnect(foreign_request, uuid4(), terminal=True)
        self.assertEqual(PresenceConnection.objects.count(), 0)
        self.device.delete()
        service.disconnect(self.request, self.tab, terminal=True)
        self.assertEqual(PresenceConnection.objects.count(), 0)
        self.assertEqual(SessionConnectionInterval.objects.count(), 0)

    def test_retention_deletes_only_old_closed_history(self):
        self.beat()
        interval = SessionConnectionInterval.objects.get()
        interval.closed_at = self.now - timedelta(days=90, seconds=1)
        interval.ended_at = interval.closed_at
        interval.save()
        self.beat(uuid4(), offset=1)
        service.maintain_history(now=self.now + timedelta(seconds=1))
        self.assertEqual(SessionConnectionInterval.objects.count(), 1)
        self.assertTrue(self.snapshot(offset=1)['is_online'])

    def test_rest_sync_and_sse_heartbeat_share_the_same_tab_identity(self):
        factory = APIRequestFactory()
        auth = self.request.auth
        for view, method, data in (
            (UserPresenceHeartbeatView, 'post', {'connection_id': str(self.tab)}),
            (RealtimeSyncView, 'get', {'presence_heartbeat': 'true', 'presence_connection_id': str(self.tab)}),
        ):
            request = getattr(factory, method)('/presence/', data, format='json')
            force_authenticate(request, user=self.user, token=auth)
            response = view.as_view()(request)
            self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(SessionConnectionInterval.objects.count(), 1)
        request = factory.post('/presence/offline/', {'connection_id': str(self.tab)}, format='json')
        force_authenticate(request, user=self.user, token=auth)
        self.assertEqual(UserPresenceOfflineView.as_view()(request).status_code, 200)
        self.beat()
        self.assertFalse(self.snapshot()['is_online'])

    def test_logout_ends_history_and_preserves_snapshot(self):
        from src.core.cms.adp.views import LogoutView
        self.beat()
        request = APIRequestFactory().post('/logout/', {}, format='json')
        force_authenticate(request, user=self.user, token=self.request.auth)
        self.assertEqual(LogoutView.as_view()(request).status_code, 204)
        interval = SessionConnectionInterval.objects.get()
        self.assertEqual(interval.end_reason, 'logout')
        self.assertEqual(interval.ended_at, self.now)
        self.assertFalse(UserDevice.objects.filter(pk=self.device.pk).exists())

    def test_legacy_clients_and_invalid_connection_id(self):
        factory = APIRequestFactory()
        for data, expected in (({}, 200), ({'connection_id': 'bad'}, 400)):
            request = factory.post('/heartbeat/', data, format='json')
            force_authenticate(request, user=self.user, token=self.request.auth)
            self.assertEqual(UserPresenceHeartbeatView.as_view()(request).status_code, expected)
        self.assertEqual(SessionConnectionInterval.objects.count(), 0)

    def test_json_scope_contract_works_without_local_callable_descriptors(self):
        with patch.object(service.bridge, 'emit', return_value=[{'tenant': 8}]) as emit:
            self.beat()
        interval = SessionConnectionInterval.objects.get()
        self.assertEqual(interval.scope, {'tenant': 8})
        self.assertEqual(emit.call_args.kwargs['claims']['device_id'], self.device.pk)

    def test_explicit_end_after_midnight_is_included_in_today(self):
        day_start = timezone.localtime(self.now).replace(hour=0, minute=0, second=0, microsecond=0)
        interval = SessionConnectionInterval.objects.create(
            user=self.user, device_key=self.device.pk, scope={'tenant': 1},
            scope_hash=service.scope_hash({'tenant': 1}), started_at=day_start - timedelta(minutes=1),
            last_seen=day_start - timedelta(seconds=10), closed_at=day_start + timedelta(seconds=5),
            ended_at=day_start + timedelta(seconds=5), end_reason='disconnect',
        )
        data = service.history(scope={'tenant': 1}, actor_ref=str(self.user.public_id),
                               start=day_start, end=self.now, now=self.now)
        self.assertEqual([row['public_id'] for row in data['results']], [str(interval.public_id)])

    def test_history_pagination_and_scope(self):
        for index in range(23):
            SessionConnectionInterval.objects.create(
                user=self.user, device_key=self.device.pk, scope={'tenant': 1},
                scope_hash=service.scope_hash({'tenant': 1}), started_at=self.now - timedelta(minutes=index),
                last_seen=self.now, closed_at=self.now, end_reason='disconnect', ended_at=self.now,
            )
        self.beat(request=SimpleNamespace(user=self.user, auth={**self.request.auth, 'tenant': 2}, META=self.request.META))
        data = service.history(scope={'tenant': 1}, actor_ref=str(self.user.public_id),
                               start=self.now - timedelta(days=1), end=self.now, page=2, now=self.now)
        self.assertEqual(data['count'], 23)
        self.assertEqual(len(data['results']), 3)
        self.assertNotIn('device_key', data['results'][0])
        self.assertEqual(service.history(scope={'tenant': 3}, actor_ref=str(self.user.public_id),
                                        start=self.now - timedelta(days=1), end=self.now, now=self.now)['count'], 0)


from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase, override_settings
from rest_framework_simplejwt.tokens import AccessToken
from src.core.cms.adp.consumers.presence import PresenceConsumer
from src.core.realtime.envelope import build_envelope


@override_settings(REALTIME_TRANSPORT='websocket', CHANNEL_LAYERS={'default': {'BACKEND': 'channels.layers.InMemoryChannelLayer'}})
class WebSocketConnectionHistoryTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='ws-connection-user')
        self.device = UserDevice.objects.create(
            user=self.user, device_name='Firefox', device_type='desktop',
            user_agent='Linux Firefox/125', ip_address='192.0.2.10', is_active=True,
        )
        self.token = AccessToken.for_user(self.user)
        self.token['device_id'] = self.device.pk
        self.token['tenant'] = 1
        dims = patch.object(service.bridge, 'emit', side_effect=lambda event, **kwargs: [
            {'tenant': kwargs['claims'].get('tenant')},
        ])
        dims.start()
        self.addCleanup(dims.stop)

    def test_real_ws_auth_ping_and_disconnect_preserve_claims_without_token_in_ping(self):
        async def scenario():
            connection = WebsocketCommunicator(PresenceConsumer.as_asgi(), '/ws/presence/',
                                                headers=[(b'user-agent', b'Linux Firefox/125')])
            connected, _ = await connection.connect()
            self.assertTrue(connected)
            await connection.send_json_to(build_envelope(topic='ws:control', event_type='ws_auth',
                                                        payload={'token': str(self.token)}))
            response = await connection.receive_json_from()
            self.assertEqual(response['type'], 'ws_auth_ok')
            tab = str(uuid4())
            await connection.send_json_to(build_envelope(topic='presence:user', event_type='presence_ping',
                                                        payload={'connection_id': tab}))
            import asyncio
            for _ in range(30):
                if await database_sync_to_async(SessionConnectionInterval.objects.exists)():
                    break
                await asyncio.sleep(0.01)
            interval = await database_sync_to_async(SessionConnectionInterval.objects.get)()
            self.assertEqual(interval.scope, {'tenant': 1})
            await connection.disconnect(code=1000)
            interval = await database_sync_to_async(SessionConnectionInterval.objects.get)()
            self.assertEqual(interval.end_reason, 'disconnect')
        async_to_sync(scenario)()

    def test_expired_connection_cannot_keep_presence_alive(self):
        async def scenario():
            consumer = PresenceConsumer()
            consumer.ws_user = self.user
            consumer.user_id = self.user.pk
            consumer.scope = {}
            consumer.ws_auth_claims = {'user_id': self.user.pk, 'device_id': self.device.pk,
                                       'tenant': 1, 'exp': timezone.now().timestamp() - 1}
            self.assertIsNone(await consumer._validated_history_request())
        async_to_sync(scenario)()
