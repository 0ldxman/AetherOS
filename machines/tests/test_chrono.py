"""Игровое время: опорные точки, скорость, сдвиги, пояса машин, правка точек и предупреждения."""
from datetime import datetime, timedelta, timezone as tz
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from machines.models import Machine, TimeAnchor
from machines.world import chrono, clock, dates

UTC = tz.utc


def at(*parts):
    return datetime(*parts, tzinfo=UTC)


class ChronoTests(TestCase):
    def setUp(self):
        self.now = at(2026, 11, 10, 7, 20)
        patcher = mock.patch("machines.world.chrono.timezone.now", return_value=self.now)
        patcher.start()
        self.addCleanup(patcher.stop)

    def anchor(self, real, game, rate=1):
        return TimeAnchor.objects.create(real_at=real, game_at=game, rate=rate)

    def test_without_anchors_time_stands_on_the_old_world_date(self):
        self.assertEqual(chrono.game_now(), dates.GAME_NOW)
        self.assertEqual(chrono.to_real(dates.GAME_NOW + timedelta(seconds=1)), None)

    def test_time_runs_from_the_last_anchor_with_its_rate(self):
        self.anchor(at(2026, 11, 10, 7, 20), at(2030, 9, 7, 9, 0))
        self.anchor(at(2026, 11, 20), at(2031, 1, 1), rate=0.5)
        self.assertEqual(chrono.to_game(at(2026, 11, 11, 7, 20)), at(2030, 9, 8, 9, 0))
        self.assertEqual(chrono.to_game(at(2026, 11, 20, 2)), at(2031, 1, 1, 1))          # прыжок вперёд и вдвое медленнее
        self.assertEqual(chrono.to_game(at(2026, 11, 9, 7, 20)), at(2030, 9, 6, 9, 0))     # до первой точки: назад по её скорости

    def test_a_record_keeps_its_game_time_after_a_shift(self):
        first = self.anchor(at(2026, 11, 1), at(2030, 1, 1))
        written = at(2026, 11, 5)
        before = chrono.to_game(written)
        self.anchor(at(2026, 11, 8), at(2029, 6, 1))                                        # назад
        chrono.forget()
        self.assertEqual(chrono.to_game(written), before)
        self.assertEqual(chrono.anchor_at(written).pk, first.pk)

    def test_to_real_finds_when_the_game_reaches_a_moment(self):
        self.anchor(at(2026, 11, 10, 7, 20), at(2030, 9, 7, 9, 0), rate=2)
        self.assertEqual(chrono.to_real(at(2030, 9, 7, 11, 0)), at(2026, 11, 10, 8, 20))
        self.anchor(at(2026, 11, 12), at(2031, 1, 1), rate=0)
        chrono.forget()
        self.assertEqual(chrono.to_real(at(2030, 12, 31)), at(2026, 11, 12))                # перепрыгнули: в момент прыжка
        self.assertIsNone(chrono.to_real(at(2031, 1, 2)))                                   # время встало раньше
        self.assertEqual(chrono.to_real(at(2020, 1, 1)), self.now)                          # уже позади

    def test_machines_show_the_same_moment_in_their_own_zone(self):
        self.anchor(at(2026, 11, 10, 7, 20), at(2031, 3, 2, 9, 0), rate=0)
        moscow = Machine.objects.create(name="M", hostname="m", time_zone="Europe/Moscow")
        tokyo = Machine.objects.create(name="T", hostname="t", time_zone="Asia/Tokyo")
        self.assertEqual(f"{clock.now(moscow):%H:%M %Z}", "12:00 MSK")
        self.assertEqual(f"{clock.now(tokyo):%H:%M}", "18:00")
        self.assertEqual(chrono.stamp(self.now, moscow), "2031-03-02 12:00")
        self.assertTrue(chrono.valid_zone("Europe/Moscow"))
        self.assertFalse(chrono.valid_zone("Mars/Olympus"))

    def test_tmset_with_an_exact_time_reads_it_in_the_zone_of_the_machine(self):
        self.anchor(at(2026, 11, 10, 7, 20), at(2031, 3, 2, 9, 0), rate=0)
        moscow = Machine.objects.create(name="M", hostname="m", time_zone="Europe/Moscow")
        self.assertEqual(clock.parse("2031-03-02 13:00", moscow, None), 3600)

    def test_the_past_is_not_rewritten_and_backward_shifts_warn(self):
        past = self.anchor(at(2026, 11, 1), at(2031, 1, 1))
        with self.assertRaises(chrono.TimeError):
            chrono.add(at(2026, 11, 2), at(2031, 2, 1))
        with self.assertRaises(chrono.TimeError):
            chrono.remove(past)
        with self.assertRaises(chrono.TimeError):
            chrono.change(past, at(2026, 12, 1), at(2031, 2, 1), 1)
        soon = chrono.add(None, at(2031, 1, 12), note="сейчас")
        self.assertEqual(soon.real_at, self.now)
        future = chrono.add(at(2026, 12, 1), at(2031, 6, 1), rate=0.33)
        chrono.change(future, at(2026, 12, 2), at(2031, 6, 2), 0.5)
        self.assertEqual(float(TimeAnchor.objects.get(pk=future.pk).rate), 0.5)
        self.assertTrue(chrono.warnings(None, at(2031, 1, 5))[0].startswith("Сдвиг назад на 7 д"))
        self.assertEqual(chrono.warnings(None, at(2031, 2, 1)), [])
        chrono.remove(future)
        self.assertFalse(TimeAnchor.objects.filter(pk=future.pk).exists())

    def test_the_browser_gets_game_time_rate_and_the_next_change(self):
        self.anchor(at(2026, 11, 10, 7, 20), at(2031, 3, 2, 9, 0), rate=0.5)
        self.anchor(at(2026, 11, 11), at(2031, 4, 1), rate=1)
        moscow = Machine.objects.create(name="M", hostname="m", time_zone="Europe/Moscow")
        found = chrono.client(moscow)
        self.assertEqual(found["game"], int(at(2031, 3, 2, 9, 0).timestamp() * 1000))
        self.assertEqual((found["rate"], found["zone"], found["offset_min"]), (0.5, "Europe/Moscow", 180))
        self.assertEqual(found["next"]["rate"], 1)
