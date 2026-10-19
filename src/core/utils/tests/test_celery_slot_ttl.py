import time
from unittest.mock import patch

from django.test import SimpleTestCase

from src.core.utils.celery.concurrency import (
    QueueConcurrencyManager,
    _start_slot_keepalive,
    _stop_slot_keepalive,
    queue_concurrency_manager,
)


class SlotTtlTests(SimpleTestCase):
    def setUp(self):
        manager = queue_concurrency_manager
        self._saved = (
            manager._use_distributed,
            manager._cache_ttl,
            dict(manager._queue_limits),
            dict(manager._queue_classes),
            manager._non_light_cap,
            manager._non_light_gate,
        )

    def tearDown(self):
        manager = queue_concurrency_manager
        (
            manager._use_distributed,
            manager._cache_ttl,
            manager._queue_limits,
            manager._queue_classes,
            manager._non_light_cap,
            manager._non_light_gate,
        ) = self._saved

    def test_touch_extends_queue_counter(self):
        manager = queue_concurrency_manager
        manager._use_distributed = True
        manager._cache_ttl = 3600
        with patch('src.core.utils.celery.concurrency.cache.touch') as touch:
            manager.touch_held_slots('long_queue')
        touch.assert_called_once_with('celery:queue_concurrency:long_queue', 3600)

    def test_touch_skips_local_mode(self):
        manager = queue_concurrency_manager
        manager._use_distributed = False
        with patch('src.core.utils.celery.concurrency.cache.touch') as touch:
            manager.touch_held_slots('long_queue')
        touch.assert_not_called()

    def test_touch_includes_non_light_counter(self):
        manager = queue_concurrency_manager
        manager._use_distributed = True
        manager._cache_ttl = 3600
        manager._non_light_cap = 2
        manager._queue_classes = {'long_queue': 'medium', 'default': 'light'}
        with patch('src.core.utils.celery.concurrency.cache.touch') as touch:
            manager.touch_held_slots('long_queue')
            manager.touch_held_slots('default')
        keys = [call.args[0] for call in touch.call_args_list]
        self.assertIn('celery:queue_concurrency:long_queue', keys)
        self.assertIn('celery:queue_concurrency:__non_light__', keys)
        self.assertIn('celery:queue_concurrency:default', keys)
        self.assertEqual(keys.count('celery:queue_concurrency:__non_light__'), 1)

    def test_touch_error_does_not_raise(self):
        manager = queue_concurrency_manager
        manager._use_distributed = True
        with patch(
            'src.core.utils.celery.concurrency.cache.touch',
            side_effect=RuntimeError('нет touch'),
        ):
            manager.touch_held_slots('long_queue')

    def test_keepalive_stops_with_the_task(self):
        manager = queue_concurrency_manager
        manager._use_distributed = True
        manager._cache_ttl = 3
        calls = []

        def record(self, queue_name):
            calls.append(queue_name)

        with patch.object(QueueConcurrencyManager, 'touch_held_slots', record):
            keeper = _start_slot_keepalive('long_queue', interval=0.05)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and not calls:
                time.sleep(0.02)
            self.assertTrue(calls)
            self.assertEqual(calls[0], 'long_queue')
            _stop_slot_keepalive(keeper)
            seen = len(calls)
            time.sleep(0.2)
            self.assertEqual(len(calls), seen)
