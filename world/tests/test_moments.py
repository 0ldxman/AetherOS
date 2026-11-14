"""Моменты мира в игровом времени: начало и конец ставят и снимают метку, триггеры на них, фильтры видимости, at, полоса, письмо всем."""
from datetime import datetime, timedelta, timezone as tz
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import get_script_prefix, reverse, set_script_prefix

from filesystem.testing import make_app
from machines.models import Machine, MachineProfile, TimeAnchor
from machines.world import chrono
from secure.access import satisfied
from terminal.testing import TerminalClient
from world import letters, moments
from world.models import WorldMoment, WorldTrigger

UTC = tz.utc


def at(*parts):
    return datetime(*parts, tzinfo=UTC)


class MomentClock(TestCase):
    """Реальное время на 2026-11-10 12:00, игровое = 2031-03-10 12:00 и идёт 1:1."""

    def setUp(self):
        super().setUp()
        self.now = at(2026, 11, 10, 12, 0)
        for target in ("machines.world.chrono.timezone.now",):
            patcher = mock.patch(target, side_effect=lambda: self.now)
            patcher.start()
            self.addCleanup(patcher.stop)
        TimeAnchor.objects.create(real_at=at(2026, 11, 1), game_at=at(2031, 3, 1), rate=1)
        chrono.forget()

    def move(self, **delta):
        self.now += timedelta(**delta)
        chrono.forget()
        moments.tick(force=True)

    def moment(self, **fields):
        values = {"name": "uplink", "title": "BOREAS UPLINK", "schedule": "daily 12:30", "duration": 30, "in_list": True, "ticker": True, "warn": 15, **fields}
        moment = WorldMoment.objects.create(**values)
        WorldMoment.objects.filter(pk=moment.pk).update(created_at=self.now - timedelta(hours=1))
        return WorldMoment.objects.get(pk=moment.pk)


class MomentTests(MomentClock):
    def test_a_moment_holds_its_flag_while_it_runs_and_triggers_see_both_edges(self):
        self.moment()
        WorldTrigger.objects.create(name="on", condition="world:uplink", repeat=True, actions=[{"do": "world_count", "name": "opened"}])
        WorldTrigger.objects.create(name="off", condition={"not": "world:uplink"}, was_true=True, repeat=True, actions=[{"do": "world_count", "name": "closed"}])
        self.move(minutes=10)
        self.assertFalse(satisfied("world:uplink", set()))
        self.assertEqual([row["state"] for row in moments.board()], ["later"])
        self.move(minutes=10)                                                          # 12:20: за 10 минут — пора предупреждать
        self.assertEqual(moments.board()[0]["state"], "soon")
        self.move(minutes=15)                                                          # 12:35: идёт
        self.assertTrue(satisfied({"all": ["world:uplink", "world:opened=1"]}, set()))
        self.assertEqual(moments.board()[0]["state"], "live")
        self.move(minutes=30)                                                          # 13:05: кончился
        self.assertTrue(satisfied({"all": [{"not": "world:uplink"}, "world:closed=1"]}, set()))

    def test_a_slot_missed_entirely_still_starts_and_ends(self):
        self.moment()
        WorldTrigger.objects.create(name="on", condition="world:uplink", actions=[{"do": "world_flag", "name": "heard"}])
        self.now += timedelta(hours=2)                                                 # никто не заходил с 12:00 до 14:00
        chrono.forget()
        moments.tick(force=True)
        self.assertTrue(satisfied({"all": ["world:heard", {"not": "world:uplink"}]}, set()))

    def test_filters_by_system_machine_group_and_condition(self):
        main = Machine.objects.create(name="Main", hostname="aether-main", system="AETHER")
        core = Machine.objects.create(name="Core", hostname="aether-core", system="VMS")
        ivan = get_user_model().objects.create_user("ivan")
        profile = MachineProfile.objects.create(machine=main, user=ivan, login="ivan", name="Ivan", freq=1, groups=["ops"])
        moment = self.moment(systems=["aether"])
        self.assertTrue(moments.visible(moment, main))
        self.assertFalse(moments.visible(moment, core))
        moment.systems, moment.machines = [], ["aether-core"]
        self.assertFalse(moments.visible(moment, main))
        moment.machines, moment.groups = [], ["ops"]
        with mock.patch("machines.access.groups.effective", return_value={"ops": (set(), False)}):
            self.assertTrue(moments.visible(moment, main, profile))
        self.assertFalse(moments.visible(moment, main, None))
        moment.groups, moment.condition = [], "uplink-key"
        self.assertFalse(moments.visible(moment, main, profile, set()))
        self.assertTrue(moments.visible(moment, main, profile, {"uplink-key"}))
        moment.condition, moment.in_list, moment.ticker = None, False, False
        self.assertFalse(moments.visible(moment, main))

    def test_manual_start_and_stop(self):
        moment = self.moment(schedule="once 2031-04-01 00:00")
        moments.start_now(moment, "автор")
        self.assertTrue(satisfied("world:uplink", set()))
        moments.stop_now(WorldMoment.objects.get(pk=moment.pk), "автор")
        self.assertFalse(satisfied("world:uplink", set()))
        self.assertEqual(moments.countdown(90061), "1d 01:01:01")


@override_settings(FORCE_SCRIPT_NAME=None)
class MomentScreenTests(TerminalClient, MomentClock):
    def setUp(self):
        super().setUp()
        previous = get_script_prefix()
        set_script_prefix("/")
        self.addCleanup(set_script_prefix, previous)
        self.main = Machine.objects.create(name="Main", hostname="aether-main", time_zone="Europe/Moscow")
        make_app(self.main, label="console", icon="terminal", path="/apps/terminal/")
        make_app(self.main, label="intercom", icon="mail", path="/apps/mail/")
        self.user = get_user_model().objects.create_user("ivan", password="pw")
        MachineProfile.objects.create(machine=self.main, user=self.user, name="Ivan", login="ivan", freq=1, mail="ivan@aether-main")
        self.client.force_login(self.user)

    def test_at_the_desktop_bar_and_next_event(self):
        from terminal.scenes.shell import _world_params

        self.moment()
        self.assertEqual(self.run_command("at")["output"], f"{'2031-03-10 15:30 MSK':<20}  {'BOREAS UPLINK':<24}  in 00:30:00")
        self.assertEqual(self.client.get(reverse("desktop_moments")).json()["rows"], [])          # до начала больше 15 минут
        self.move(minutes=20)
        rows = self.client.get(reverse("desktop_moments")).json()["rows"]
        self.assertEqual((rows[0]["state"], rows[0]["left"]), ("soon", 600))
        self.assertEqual(_world_params("aether-main")["next_event"], "BOREAS UPLINK at 2031-03-10 15:30 MSK")
        self.move(minutes=15)
        self.assertIn("ends in 00:25:00", self.run_command("at")["output"])

    def test_events_card_shows_upcoming_like_at(self):
        self.moment()
        rows = self.client.get(reverse("desktop_cards_events")).json()["rows"]
        self.assertEqual((rows[0]["title"], rows[0]["state"], rows[0]["left"]), ("BOREAS UPLINK", "later", 1800))      # как в at, не только скорые

    def test_a_letter_to_everyone_arrives_once(self):
        from filesystem.models import Item
        from mail.boxes import Box

        letter = Item.objects.create(slug="all-hands", name="all-hands.msg", format="msg", body="From: core@aether-core\nSubject: All hands\n\nReport.")
        letters.send_all(letter, systems=[], machines=["aether-main"], source="триггер")
        letters.send_all(letter, machines=["elsewhere"])
        box = Box.of_profile(MachineProfile.objects.get(login="ivan"), user=self.user)
        self.assertEqual(letters.deliver(box), 1)
        self.assertEqual(letters.deliver(box), 0)
