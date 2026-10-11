"""Сборка URL писем уведомлений из Vue-route (без pk в query)."""

from __future__ import annotations

from types import SimpleNamespace

from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from src.core.notifications.email_templates import _resolve_action_url
from src.core.notifications.frontend_route_url import (
    build_frontend_url_from_route,
    fill_vue_path,
    inbox_url,
)

_PATH_INDEX = {
    'ItemDetail': '/items/:taskId?',
    'ItemRequest': '/records/:requestId',
    'ItemEquipment': '/assets/:equipmentId',
    'ItemInbox': '/inbox',
}

_TASK_ID = 'a9950227-d5c5-4c01-b9b8-f6d6ab81497d'
_REQUEST_ID = '8a5738e5-bb14-4d21-bb90-9463739435f9'
_BASE = 'https://app.example.test'


class FillVuePathTests(SimpleTestCase):
    def test_optional_param_present(self):
        self.assertEqual(
            fill_vue_path('/items/:taskId?', {'taskId': _TASK_ID}),
            f'/items/{_TASK_ID}',
        )

    def test_optional_param_absent(self):
        self.assertEqual(fill_vue_path('/items/:taskId?', {}), '/items')

    def test_required_param_missing(self):
        self.assertIsNone(fill_vue_path('/records/:requestId', {}))


class BuildFrontendUrlFromRouteTests(SimpleTestCase):
    def test_item_detail_with_uuid(self):
        url = build_frontend_url_from_route(
            {'name': 'ItemDetail', 'params': {'taskId': _TASK_ID}},
            base_url=_BASE,
            path_index=_PATH_INDEX,
        )
        self.assertEqual(url, f'{_BASE}/items/{_TASK_ID}')

    def test_item_request_detail(self):
        url = build_frontend_url_from_route(
            {'name': 'ItemRequest', 'params': {'requestId': _REQUEST_ID}},
            base_url=_BASE,
            path_index=_PATH_INDEX,
        )
        self.assertEqual(url, f'{_BASE}/records/{_REQUEST_ID}')

    def test_item_inbox(self):
        url = build_frontend_url_from_route(
            {'name': 'ItemInbox'},
            base_url=_BASE,
            path_index=_PATH_INDEX,
        )
        self.assertEqual(url, f'{_BASE}/inbox')

    def test_query_appended_without_numeric_pk(self):
        url = build_frontend_url_from_route(
            {
                'name': 'ItemInbox',
                'query': {'incoming': _REQUEST_ID, 'open': 38, 'tab': 'support'},
            },
            base_url=_BASE,
            path_index=_PATH_INDEX,
        )
        self.assertEqual(
            url,
            f'{_BASE}/inbox?incoming={_REQUEST_ID}&tab=support',
        )
        self.assertNotIn('open=', url)

    def test_unknown_route(self):
        self.assertIsNone(
            build_frontend_url_from_route(
                {'name': 'UnknownRoute'},
                base_url=_BASE,
                path_index=_PATH_INDEX,
            )
        )

    def test_live_index_notifications_path(self):
        url = build_frontend_url_from_route(
            {'name': 'UserNotifications'},
            base_url=_BASE,
        )
        self.assertEqual(url, f'{_BASE}/user/notifications')


@override_settings(FRONTEND_BASE_URL=_BASE)
class ResolveActionUrlTests(SimpleTestCase):
    def test_route_without_open_pk(self):
        notification = SimpleNamespace(
            pk=38,
            link_url='',
            route={'name': 'ItemDetail', 'params': {'taskId': _TASK_ID}},
        )
        with patch(
            'src.core.notifications.email_templates.build_frontend_url_from_route',
            return_value=f'{_BASE}/items/{_TASK_ID}',
        ):
            url = _resolve_action_url(notification)
        self.assertEqual(url, f'{_BASE}/items/{_TASK_ID}')
        self.assertNotIn('open=', url)
        self.assertNotIn('38', url)

    def test_unknown_route_falls_back_to_inbox(self):
        notification = SimpleNamespace(
            pk=38,
            link_url='',
            route={'name': 'UnknownRoute'},
        )
        with patch(
            'src.core.notifications.email_templates.build_frontend_url_from_route',
            return_value=None,
        ):
            url = _resolve_action_url(notification)
        self.assertEqual(url, inbox_url(_BASE))
        self.assertNotIn('open=', url)

    def test_relative_link_url(self):
        notification = SimpleNamespace(
            pk=38,
            link_url='/items',
            route=None,
        )
        self.assertEqual(_resolve_action_url(notification), f'{_BASE}/items')

    def test_route_query_gets_scope_ref(self):
        notification = SimpleNamespace(
            pk=38,
            link_url='',
            scope_ref=_REQUEST_ID,
            route={
                'name': 'ItemDetail',
                'params': {'taskId': _TASK_ID},
                'query': {'invoice': _REQUEST_ID},
            },
        )
        with patch(
            'src.core.notifications.email_templates.build_frontend_url_from_route',
        ) as mocked:
            mocked.return_value = (
                f'{_BASE}/items/{_TASK_ID}'
                f'?invoice={_REQUEST_ID}&scope_ref={_REQUEST_ID}'
            )
            url = _resolve_action_url(notification)
        self.assertIn(f'scope_ref={_REQUEST_ID}', url)
        passed_route = mocked.call_args.args[0]
        self.assertEqual(passed_route['query']['scope_ref'], _REQUEST_ID)
        self.assertEqual(passed_route['query']['invoice'], _REQUEST_ID)
