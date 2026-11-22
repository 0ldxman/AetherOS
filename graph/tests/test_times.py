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

    def test_seconds_show_only_when_set(self):
        self.assertEqual(times.text(GAME.replace(second=15)), "2031-05-14 21:00:15")
        self.assertEqual(times.parse("2031-05-14 21:00:15").second, 15)
        self.assertEqual(times.clock_full("21:00:15"), (21, 0, 15))

    def test_shift_diff_zone_parts(self):
        self.assertEqual(times.shift("2031-05-14 21:00", minutes=-90), "2031-05-14 19:30")
        self.assertEqual(times.shift("2031-05-14 21:00", days=1, seconds=5), "2031-05-15 21:00:05")
        self.assertEqual(times.diff("2031-05-15 21:00", "2031-05-14 21:00", "hours"), 24)
        self.assertEqual(times.diff("2031-05-14 21:00:30", "2031-05-14 21:00", "seconds"), 30)
        self.assertEqual(times.diff("x", "2031-05-14 21:00"), 0)
        self.assertEqual(times.in_zone("2031-05-14 21:00", "Asia/Tokyo"), "2031-05-15 06:00")
        self.assertEqual(times.in_zone("2031-05-14 21:00", "Mars/Base"), "")
        parts = times.parts("2031-05-14 21:00")
        self.assertEqual((parts["weekday"], parts["date"], parts["clock"]), (3, "2031-05-14", "21:00"))
        tokyo = Machine.objects.create(name="T", hostname="tokyo", time_zone="Asia/Tokyo")
        self.assertEqual(times.parts("2031-05-14 21:00", tokyo)["weekday"], 4)

    def test_time_node(self):
        with mock.patch("graph.times.now", return_value=GAME.replace(second=7)):
            self.assertEqual(times.outputs(times.moment()), {"value": "2031-05-14 21:00:07", "date": "2031-05-14", "clock": "21:00:07", "year": 2031, "month": 5, "day": 14, "hour": 21, "minute": 0, "weekday": 3})
            self.assertEqual(times.text(times.moment("date")), "2031-05-14 00:00")
            self.assertEqual(times.text(times.moment("clock", "other", "09:30")), "2031-05-14 09:30")
            self.assertEqual(times.text(times.moment("clock", "other", "2030-01-01 08:15")), "2031-05-14 08:15")
            self.assertEqual(times.text(times.moment("date", "other", "2031-06-01 10:30")), "2031-06-01 00:00")
            self.assertIsNone(times.moment("datetime", "other", "вчера"))

    def test_nodes_and_compare(self):
        with mock.patch("graph.times.now", return_value=GAME):
            nodes = [node("now", "time.get"), node("back", "time.calc", mode="shift", minutes=-30), node("d", "time.calc", unit="minutes"),
                     node("z", "time.zone", zone="Asia/Tokyo"), node("p", "time.get", source="other"), node("lt", "compare", op="lt"),
                     node("eq", "compare", op="eq", b="2031-05-14 21:00"), node("t", "text", value="{когда}!", subs=[{"id": "s1", "name": "когда"}])]
            wires = [wire("now", "value", "back", "f:a"), wire("back", "shifted", "d", "f:b"), wire("now", "value", "d", "f:a"),
                     wire("now", "value", "z", "f:value"), wire("back", "shifted", "p", "f:value"), wire("back", "shifted", "lt", "f:a"),
                     wire("now", "value", "lt", "f:b"), wire("now", "value", "eq", "f:a"), wire("now", "date", "t", "f:s1")]
            self.assertEqual(self.value(nodes, wires, "back", "shifted"), "2031-05-14 20:30")
            self.assertEqual(self.value(nodes, wires, "d", "diff"), 30)
            self.assertEqual(self.value(nodes, wires, "z"), "2031-05-15 06:00")
            self.assertEqual(self.value(nodes, wires, "p", "minute"), 30)
            self.assertTrue(self.value(nodes, wires, "lt"))
            self.assertTrue(self.value(nodes, wires, "eq"))
            self.assertEqual(self.value(nodes, wires, "t"), "2031-05-14!")
        kind = N.KINDS["time.calc"]
        self.assertEqual((N.sockets(kind, {}, "out"), N.sockets(kind, {"mode": "shift"}, "out")), (["diff"], ["shifted"]))

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


class PartsUpgradeTests(TestCase):
    def test_old_parts_node_becomes_a_time_node_with_the_same_outputs(self):
        from graph.upgrade import time_parts

        doc = {"nodes": [{"id": "p", "type": "time.parts", "data": {"value": "2031-05-14 21:00", "machine": "core"}}], "wires": [], "groups": {"g": {"nodes": [{"id": "q", "type": "time.parts", "data": {}}]}}}
        self.assertTrue(time_parts(doc))
        self.assertEqual((doc["nodes"][0]["type"], doc["nodes"][0]["data"]), ("time.get", {"value": "2031-05-14 21:00", "source": "other"}))
        self.assertEqual((doc["groups"]["g"]["nodes"][0]["type"], doc["groups"]["g"]["nodes"][0]["data"]["source"]), ("time.get", "now"))
        self.assertFalse(time_parts(doc))
