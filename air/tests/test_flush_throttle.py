"""Нагрузка: опросы эфира прореживают выпуск наступившего, чистка служебных таблиц, кэш ошибок сценария, факты игрока на проход."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from air import events


class AirFlushThrottleTests(TestCase):
    def setUp(self):
        cache.delete("air:flush")
        self.addCleanup(cache.delete, "air:flush")

    def test_polls_flush_at_most_once_per_window_and_explicit_calls_always(self):
        with mock.patch.object(events, "FLUSH_EVERY", 2), mock.patch.object(events, "flush_broadcasts", return_value=0) as broadcasts, \
                mock.patch.object(events, "flush_replies", return_value=0):
            events.flush(throttled=True)
            events.flush(throttled=True)                     # тот же интервал: пропущен
            self.assertEqual(broadcasts.call_count, 1)
            events.flush()                                   # не из опроса: всегда
            self.assertEqual(broadcasts.call_count, 2)
