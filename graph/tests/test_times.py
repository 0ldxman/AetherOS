"""Тип «Дата и время»: разбор, сдвиг, разница, части (в поясе машины), сравнение дат, «Ждать до» даты, последняя активность сессии."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from graph import nodes as N, runtime, sessions, times
from graph.models import Graph, Run
from graph.tests.test_runtime import node, wire
from machines.models import Machine, MachineProfile, Session

GAME = datetime(2031, 5, 14, 21, 0, tzinfo=dt_timezone.utc)                      # среда


class TimeTests(TestCase):
    def value(self, nodes, wires, node_id, out="value"):
        doc = runtime.Doc(runtime.flatten({"nodes": nodes, "wires": wires}, "g"))
        return runtime.value_of(Run(graph=Graph(slug="g"), user=None, ctx={}, state={}), doc, node_id, out)

    def test_parse_and_text(self):
        self.assertEqual(times.parse("2031-05-14 21:00"), GAME)
        self.assertEqual(times.parse("2031-05-14T21:00"), GAME)
        self.assertIsNone(times.parse("вчера"))
        self.assertIsNone(times.parse("сейчас", words=False))
        self.assertEqual(times.text(GAME), "2031-05-14 21:00")
        self.assertEqual(times.clock("9:05"), (9, 5))

    def test_shift_diff_parts(self):
        self.assertEqual(times.shift("2031-05-14 21:00", -90), "2031-05-14 19:30")
        self.assertEqual(times.shift("2031-05-14 21:00", 1, "days"), "2031-05-15 21:00")
        self.assertEqual(times.diff("2031-05-15 21:00", "2031-05-14 21:00", "hours"), 24)
        self.assertEqual(times.diff("x", "2031-05-14 21:00"), 0)
        parts = times.parts("2031-05-14 21:00")
        self.assertEqual((parts["weekday"], parts["date"], parts["clock"]), (3, "2031-05-14", "21:00"))
        tokyo = Machine.objects.create(name="T", hostname="tokyo", time_zone="Asia/Tokyo")
        self.assertEqual(times.parts("2031-05-14 21:00", tokyo)["clock"], "06:00")                 # UTC+9: уже четверг
        self.assertEqual(times.parts("2031-05-14 21:00", tokyo)["weekday"], 4)

    def test_nodes_and_compare(self):
        with mock.patch("graph.times.now", return_value=GAME):
            nodes = [node("now", "time.now"), node("back", "time.shift", amount=-30), node("d", "time.diff", unit="minutes"),
                     node("p", "time.parts"), node("lt", "compare", op="lt"), node("eq", "compare", op="eq", b="2031-05-14 21:00")]
            wires = [wire("now", "value", "back", "f:value"), wire("back", "value", "d", "f:b"), wire("now", "value", "d", "f:a"),
                     wire("back", "value", "p", "f:value"), wire("back", "value", "lt", "f:a"), wire("now", "value", "lt", "f:b"),
                     wire("now", "value", "eq", "f:a")]
            self.assertEqual(self.value(nodes, wires, "back"), "2031-05-14 20:30")
            self.assertEqual(self.value(nodes, wires, "d"), 30)
            self.assertEqual(self.value(nodes, wires, "p", "minute"), 30)
            self.assertTrue(self.value(nodes, wires, "lt"))
            self.assertTrue(self.value(nodes, wires, "eq"))

    def test_date_fields_are_mixed(self):
        self.assertEqual(N.sock_type(N.KINDS["wait"], {}, "in", "f:at"), "datetime|text")
        self.assertTrue(N.compatible("datetime", "datetime|text") and N.compatible("text", "datetime|text"))
        self.assertTrue(N.compatible("datetime", "text"))

    def test_wait_until_a_date(self):
        from machines.world import chrono

        with mock.patch.object(chrono, "to_real", side_effect=lambda game, after=None: game):
            self.assertEqual(runtime.until_clock("2031-05-14 21:00"), GAME)

    def test_last_activity_of_a_session(self):
        user = get_user_model().objects.create_user("ivan")
        machine = Machine.objects.create(name="Main", hostname="aether-main")
        profile = MachineProfile.objects.create(machine=machine, user=user, login="ivan", name="ivan", freq=1)
        real = timezone.now() - timedelta(hours=1)
        Session.objects.create(user=user, profile=profile, seen_at=real)
        with mock.patch("machines.world.chrono.to_game", return_value=GAME):
            self.assertEqual(sessions.props("ivan/ivan@aether-main")["seen"], "2031-05-14 21:00")
        self.assertEqual(sessions.props("ivan/root@aether-main")["seen"], "")
