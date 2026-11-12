"""События эфира в игровом времени: окна полос, передачи по расписанию, ответчики."""
from datetime import datetime, timedelta, timezone as tz
from decimal import Decimal
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.test import TestCase

from air import events, radio, schedule
from air.models import Band, Broadcast, Responder, Station, Transmission
from machines.models import TimeAnchor
from machines.world import chrono

UTC = tz.utc


def at(*parts):
    return datetime(*parts, tzinfo=UTC)


class ScheduleTests(TestCase):
    def test_lines_and_latest_slot(self):
        lines = schedule.parse("daily 21:00\nhourly :15\n# комментарий")
        self.assertEqual(schedule.latest(lines, at(2031, 3, 2, 21, 10)), at(2031, 3, 2, 21, 0))
        self.assertEqual(schedule.latest(lines, at(2031, 3, 2, 21, 20)), at(2031, 3, 2, 21, 15))
        weekdays = schedule.parse("mon-fri 09:00")
        self.assertEqual(schedule.latest(weekdays, at(2031, 3, 2, 12, 0)), at(2031, 2, 28, 9, 0))     # 2 марта 2031 воскресенье
        self.assertEqual(schedule.latest(schedule.parse("every 30m"), at(2031, 3, 2, 10, 44)), at(2031, 3, 2, 10, 30))
        self.assertIsNone(schedule.latest(schedule.parse("once 2031-03-05 21:00"), at(2031, 3, 2)))
        moscow = at(2031, 3, 2, 18, 30).astimezone(ZoneInfo("Europe/Moscow"))
        self.assertEqual(schedule.latest(schedule.parse("daily 21:00"), moscow), at(2031, 3, 2, 18, 0))
        self.assertTrue(schedule.problems("daily 25:00")[0].startswith("строка 1"))
        self.assertTrue(schedule.problems("weekly 21:00"))
        self.assertEqual(schedule.describe(schedule.parse("sat,sun 10:00")), "sat,sun в 10:00")


class AirEventsTests(TestCase):
    def setUp(self):
        self.now = at(2026, 11, 10, 12, 0)
        for target in ("air.radio.timezone.now", "air.events.timezone.now", "machines.world.chrono.timezone.now"):
            patcher = mock.patch(target, side_effect=lambda: self.now)
            patcher.start()
            self.addCleanup(patcher.stop)
        TimeAnchor.objects.create(real_at=at(2026, 11, 1), game_at=at(2031, 3, 1), rate=1)    # игровое = реальное + 4 г 4 мес
        self.ivan = get_user_model().objects.create_user("ivan")
        self.olga = get_user_model().objects.create_user("olga")
        self.boreas = Station.objects.create(name="BOREAS")

    def game(self):
        return chrono.to_game(self.now)

    def move(self, **delta):
        self.now += timedelta(**delta)

    def heard(self, user, freq="7.115", since=None):
        return [row["text"] for row in radio.listen(user, freq, since or self.now - timedelta(hours=2), now=self.now)]

    def test_window_closes_the_band_and_its_edges_crumble(self):
        game = self.game()                                                    # 2031-03-10 12:00, понедельник
        Band.objects.create(low=Decimal("7.100"), high=Decimal("7.200"), kind="open", window=f"*: {game:%H}:30-23:00")
        with self.assertRaises(radio.AirError):
            radio.transmit(self.ivan, "7.115", "anyone?", now=self.now)       # за 30 минут до окна: тишина
        self.move(minutes=25)                                                 # за 5 минут: край окна
        sent = radio.transmit(self.ivan, "7.115", "boreas boreas boreas boreas", now=self.now)
        text = self.heard(self.olga)[0]
        self.assertIn(events.NOISE, text)
        self.assertEqual(len(text), len(sent.text))
        self.assertEqual(self.heard(self.olga)[0], text)                      # рассыпается одинаково, не мигает
        self.move(minutes=10)
        radio.transmit(self.ivan, "7.115", "clear now", now=self.now)
        self.assertEqual(self.heard(self.olga)[-1], "clear now")

    def test_a_broadcast_airs_once_per_slot_and_texts_go_round(self):
        game = self.game()
        Broadcast.objects.create(station=self.boreas, freq=Decimal("7.115"), texts=["ONE", "TWO"], schedule="hourly :15",
                                 created_at=self.now - timedelta(hours=3))
        tuned = self.now
        self.assertEqual(self.heard(self.olga, since=tuned), [])                # слот 11:15 игрового был до выхода на частоту
        self.move(minutes=20)                                                   # прошёл 12:15
        self.assertEqual(self.heard(self.olga, since=tuned), ["TWO"])
        self.assertEqual(self.heard(self.olga, since=tuned), ["TWO"])           # повторно не выходит
        self.move(hours=5)                                                      # пропущенные слоты не догоняются: только последний
        self.assertEqual(self.heard(self.olga, since=tuned), ["TWO", "ONE"])
        self.assertEqual(Transmission.objects.filter(broadcast__isnull=False).count(), 3)
        self.assertEqual(game.minute, 0)

    def test_a_shift_back_does_not_repeat_aired_slots(self):
        Broadcast.objects.create(station=self.boreas, freq=Decimal("7.115"), texts=["NEWS"], schedule="hourly :00",
                                 created_at=self.now - timedelta(hours=3))
        events.flush(self.now)
        TimeAnchor.objects.create(real_at=self.now + timedelta(minutes=1), game_at=self.game() - timedelta(hours=3), rate=1)
        chrono.forget()
        self.move(minutes=70)
        events.flush(self.now)
        self.assertEqual(Transmission.objects.filter(broadcast__isnull=False).count(), 1)

    def test_a_broadcast_with_a_condition_is_heard_only_with_the_key(self):
        Broadcast.objects.create(station=self.boreas, freq=Decimal("7.115"), texts=["SECRET"], schedule="hourly :05",
                                 condition="boreas-key", created_at=self.now - timedelta(hours=1))
        self.move(minutes=10)
        self.assertEqual(self.heard(self.olga), [])
        texts = [row["text"] for row in radio.listen(self.olga, "7.115", self.now - timedelta(hours=2), now=self.now, keys={"boreas-key"})]
        self.assertEqual(texts, ["SECRET"])

    def test_a_responder_answers_after_a_delay_once_per_cooldown(self):
        from mail.models import Flag

        Responder.objects.create(station=self.boreas, freq=Decimal("7.115"), pattern="qsl\nкто там", reply="{callsign} DE BOREAS QSL",
                                 delay=30, cooldown=10, actions=[{"do": "flag", "name": "met-boreas"}])
        box = mock.Mock(user=self.ivan)
        radio.transmit(self.ivan, "7.115", "boreas, кто там?", now=self.now, box=None)
        self.assertEqual(self.heard(self.olga), ["boreas, кто там?"])
        self.move(seconds=31)
        self.assertEqual(self.heard(self.olga)[-1], "IVAN DE BOREAS QSL")
        self.move(minutes=1)
        radio.transmit(self.ivan, "7.115", "QSL?", now=self.now)
        self.move(minutes=1)
        self.assertEqual(self.heard(self.olga).count("IVAN DE BOREAS QSL"), 1)          # пауза для этого игрока
        self.assertFalse(Flag.objects.filter(user=self.ivan).exists())                   # без ящика исходов нет
        self.move(minutes=11)
        with mock.patch("mail.talk._apply") as apply:
            radio.transmit(self.ivan, "7.115", "qsl", now=self.now, box=box)
        apply.assert_called_once()
        self.assertFalse(events.matches(Responder(pattern="qsl"), "qslx"))
        self.assertTrue(events.matches(Responder(pattern=r"^bor\w+", regex=True), "Boreas?"))
        self.assertEqual(events.pattern_problems("(", True)[0][:3], "«(»")
