"""Атрибуты (одна сторона сущности), «Операционная система», «Машина: Изменить состояние» и перевод старых графов."""
from datetime import datetime, timezone as dt_timezone

from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from graph import check, nodes as N, runtime, upgrade
from graph.models import Run
from graph.runtime import Doc, value_of
from graph.tests.test_runtime import make, node, wire
from machines.models import AccountBlock, Machine, MachineProfile, MachineProfileToken, SystemType


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


class AttributeTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        SystemType.objects.update_or_create(code="VMSX", defaults={"name": "VMS X", "path_style": "vms", "greeting": "hello {login}"})
        self.core = Machine.objects.create(name="Core", hostname="core", system="VMSX", lag_ms=800, noise_pct=3, time_zone="Asia/Tokyo",
                                           booted_at=datetime(2031, 3, 2, 14, 5, tzinfo=dt_timezone.utc))
        Machine.objects.create(name="Edge", hostname="edge", system="VMSX")
        self.ops = MachineProfile.objects.create(machine=self.core, login="ops", endpoints=["22.000"], groups=["staff"], root=True)

    def get(self, nodes, wires, node_id, out):
        run = type("R", (), {"user": self.ivan, "state": {}, "ctx": {}})()
        return value_of(run, Doc({"nodes": nodes, "wires": wires}), node_id, out)

    def test_group_and_catalog(self):
        self.assertEqual(N.KINDS["attr:machine.state"].group, N.ATTR)
        self.assertIn({"name": N.ATTR, "label": "Атрибуты"}, N.catalog()["groups"])
        self.assertNotIn("lag_ms", [s.name for s in N.DATA_OUTS["ent:machine"]])
        self.assertNotIn("blocked", [s.name for s in N.DATA_OUTS["ent:account"]])

    def test_machine_state_from_entity_wire(self):
        nodes = [node("m", "ent:machine", machine="core"), node("s", "attr:machine.state")]
        wires = [f("m", "value", "s", "machine")]
        self.assertEqual([self.get(nodes, wires, "s", o) for o in ("lag_ms", "noise_pct", "screen_noise", "defects")], [800, 3.0, 0, True])
        Machine.objects.filter(pk=self.core.pk).update(lag_ms=0, noise_pct=0)
        self.assertFalse(self.get(nodes, wires, "s", "defects"))
        self.assertEqual([p for p in check.problems({"nodes": nodes, "wires": wires}) if p["level"] == "error"], [])

    def test_machine_time(self):
        nodes = [node("t", "attr:machine.time", machine="core")]
        self.assertEqual(self.get(nodes, [], "t", "zone"), "Asia/Tokyo")
        self.assertEqual(self.get(nodes, [], "t", "booted"), "2031-03-02 14:05")
        self.assertRegex(self.get(nodes, [], "t", "local"), r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}")
        self.assertIsInstance(self.get(nodes, [], "t", "uptime"), int)
        self.assertEqual(self.get([node("t", "attr:machine.time", machine="nope")], [], "t", "uptime"), 0)

    def test_account_access(self):
        from machines.world import edits

        edits.set_keys(self.ops, "cardkey and badge")
        alive = edits.create_token(self.ops)
        MachineProfileToken.objects.create(profile=self.ops, token="tk-used", max_usage=1, usage=1)
        nodes = [node("u", "ent:account", account="ops@core"), node("a", "attr:account.access")]
        wires = [f("u", "value", "a", "account")]
        got = [self.get(nodes, wires, "a", o) for o in ("groups", "endpoints", "root", "blocked", "keys", "tokens")]
        self.assertEqual(got, [["staff"], ["22.000"], True, False, "cardkey and badge", [alive]])
        AccountBlock.objects.create(profile=self.ops, user=self.ivan, until=datetime(2999, 1, 1, tzinfo=dt_timezone.utc))
        self.assertTrue(self.get(nodes, wires, "a", "blocked"))

    def test_os_entity(self):
        nodes = [node("m", "ent:machine", machine="core"), node("o", "ent:os")]
        wires = [f("m", "system", "o", "system")]
        self.assertEqual(N.data_out(N.KINDS["ent:machine"], "system").type, "os")
        got = [self.get(nodes, wires, "o", o) for o in ("value", "code", "name", "dialect", "greeting", "machines")]
        self.assertEqual(got, ["VMSX", "VMSX", "VMS X", "vms", "hello {login}", ["core", "edge"]])
        self.assertTrue(N.compatible("os", "text"))
        self.assertEqual([p for p in check.problems({"nodes": nodes, "wires": wires}) if p["level"] == "error"], [])


class StateActTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.core = Machine.objects.create(name="Core", hostname="core", lag_ms=500, noise_pct=95)

    def act(self, **data):
        graph = make([node("m", "manual"), node("a", "act:machine.state", machine="core", **data), node("bad", "act:tag", variant="on", name="bad")],
                     [wire("m", "fire", "a"), wire("a", "fail", "bad")], slug=f"s{Run.objects.count()}")
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        self.core.refresh_from_db()

    def test_set_keeps_empty_fields(self):
        self.act(mode="set", drop_pct="5", overload_pct="15")
        self.assertEqual((self.core.lag_ms, self.core.noise_pct, self.core.drop_pct, self.core.overload_pct), (500, 95, 5, 15))

    def test_add_clamps(self):
        self.act(mode="add", noise_pct="10", lag_ms="-800", screen_noise="30")
        self.assertEqual((self.core.noise_pct, self.core.lag_ms, self.core.screen_noise), (100, 0, 30))

    def test_reset(self):
        self.act(mode="reset", lag_ms="999")
        self.assertEqual((self.core.lag_ms, self.core.noise_pct, self.core.screen_noise), (0, 0, 0))

    def test_not_a_number_fails(self):
        self.act(mode="set", lag_ms="много")
        self.assertTrue(values.on("world", 0, "bad"))


class UpgradeTests(TestCase):
    def test_old_wires_move_to_attributes(self):
        doc = {"nodes": [node("m", "ent:machine", machine="core"), node("u", "ent:account", account="ops@core"),
                         node("c", "compare"), node("b", "boolean")],
               "wires": [f("m", "lag_ms", "c", "a"), f("m", "noise_pct", "c", "b"), f("m", "name", "c", "a"), f("u", "blocked", "b", "value")],
               "groups": {"g1": {"title": "Г", "nodes": [node("x", "act:machine.change", variant="screen_noise", machine="core", screen_noise=40),
                                                          node("y", "act:machine.change", variant="name", machine="core", name="z")], "wires": []}}}
        self.assertTrue(upgrade.attributes(doc))
        types = {n["id"]: n["type"] for n in doc["nodes"]}
        self.assertEqual(types["m-machine-state"], "attr:machine.state")
        self.assertEqual(types["u-account-access"], "attr:account.access")
        moved = [(w["from"], w["out"]) for w in doc["wires"]]
        self.assertEqual(moved[:4], [("m-machine-state", "lag_ms"), ("m-machine-state", "noise_pct"), ("m", "name"), ("u-account-access", "blocked")])
        self.assertIn(("m", "value", "m-machine-state", "f:machine"), [(w["from"], w["out"], w["to"], w["in"]) for w in doc["wires"]])
        inner = doc["groups"]["g1"]["nodes"]
        self.assertEqual((inner[0]["type"], inner[0]["data"]), ("act:machine.state", {"mode": "set", "machine": "core", "screen_noise": 40}))
        self.assertEqual(inner[1]["type"], "act:machine.change")
        self.assertFalse(upgrade.attributes(doc))


class PlayerEntityTests(TestCase):
    def test_accounts_and_sessions(self):
        from machines.models import Session

        ivan = get_user_model().objects.create_user("ivan")
        core = Machine.objects.create(name="Core", hostname="core")
        mine = MachineProfile.objects.create(machine=core, login="ivan", user=ivan)
        ops = MachineProfile.objects.create(machine=core, login="ops")
        Session.objects.create(user=ivan, profile=ops)
        run = type("R", (), {"user": ivan, "state": {}, "ctx": {}})()
        doc = Doc({"nodes": [node("p", "ent:player")], "wires": []})
        self.assertEqual(value_of(run, doc, "p", "accounts"), ["ivan@core"])
        self.assertEqual(value_of(run, doc, "p", "sessions"), ["ivan/ops@core"])
        self.assertEqual(mine.user, ivan)


class WroteOutsTests(TestCase):
    def test_outputs_by_channel(self):
        kind = N.KINDS["on:character.wrote"]
        outs = lambda channel: [s.name for s in N.DATA_OUTS[kind.name] if N._out_on(kind, {"channel": channel}, s.name)]   # noqa: E731
        self.assertEqual(outs("any"), ["character", "channel", "subject", "sender", "text", "message", "player"])
        self.assertEqual(outs("mail"), ["character", "channel", "subject", "from_address", "text", "message", "player"])
        self.assertEqual(outs("forum"), ["character", "channel", "subject", "nick", "text", "message", "player"])
        self.assertEqual(outs("air"), ["character", "channel", "freq", "callsign", "text", "message", "player"])

    def test_old_wires(self):
        doc = {"nodes": [node("a", "on:character.wrote", channel="air"), node("m", "on:character.wrote", channel="mail"),
                         node("x", "on:character.wrote"), node("t", "text")],
               "wires": [f("a", "sender", "t", "value"), f("a", "subject", "t", "value"), f("m", "sender", "t", "value"),
                         f("x", "sender", "t", "value")]}
        self.assertTrue(upgrade.wrote_outs(doc))
        self.assertEqual([(w["from"], w["out"]) for w in doc["wires"]], [("a", "callsign"), ("m", "from_address"), ("x", "sender")])
        self.assertFalse(upgrade.wrote_outs(doc))


class EventsTests(TestCase):
    def test_events_group(self):
        groups = {name: N.KINDS[name].group for name in ("manual", "signal", "on:time", "on:tag", "on:layer.added", "on:air.station",
                                                         "on:air.sent", "on:layer.changed", "on:object.got", "while")}
        self.assertEqual({name for name, group in groups.items() if group == N.HAPPEN},
                         {"manual", "signal", "on:time", "on:tag", "on:layer.added", "on:air.station"})
        self.assertEqual(groups["while"], N.NOUN)
        self.assertNotIn("added", [s.name for s in N.KINDS["on:layer.changed"].outs])

    def test_air_split(self):
        from engine.events import emit
        from graph.models import Run

        ivan = get_user_model().objects.create_user("ivan")
        make([node("p", "on:air.sent", repeat="always"), node("a", "do:world_count", name="player")], [wire("p", "sent", "a")], slug="ap")
        make([node("s", "on:air.station", repeat="always"), node("b", "do:world_count", name="station")], [wire("s", "sent", "b")], slug="as")
        emit("air.sent", ivan, freq="14.230", callsign="IV1", text="hi", by="player")
        emit("air.sent", None, freq="14.230", callsign="KT", text="yo", by="station")
        self.assertEqual((values.get(values.COUNT, "world", 0, "player"), values.get(values.COUNT, "world", 0, "station")), (1, 1))
        self.assertEqual(Run.objects.count(), 2)

    def test_object_got_from_scenario_is_not_a_trigger(self):
        kind = N.KINDS["on:object.got"]
        event = type("E", (), {"data": {"via": "scenario", "item": "x", "path": "/a"}, "host": "core", "login": "ops"})()
        self.assertFalse(kind.match({"via": "any"}, "got", event))
        event.data["via"] = "archive"
        self.assertTrue(kind.match({"via": "any"}, "got", event))

    def test_upgrade(self):
        doc = {"nodes": [node("a", "on:air.sent", by="station", character="kate"), node("b", "on:air.sent", by="any", character="kate"),
                         node("l", "on:layer.changed", type="password"), node("m", "manual"), node("t", "act:tag")],
               "wires": [wire("m", "fire", "l"), wire("l", "added", "t"), wire("l", "removed", "t")]}
        self.assertTrue(upgrade.events(doc))
        kinds = {n["id"]: (n["type"], n["data"]) for n in doc["nodes"]}
        self.assertEqual(kinds["a"], ("on:air.station", {"character": "kate"}))
        self.assertEqual(kinds["b"], ("on:air.sent", {}))
        self.assertEqual(kinds["l-added"], ("on:layer.added", {"type": "password"}))
        pairs = [(w["from"], w["out"], w["to"]) for w in doc["wires"]]
        self.assertIn(("l-added", "added", "t"), pairs)
        self.assertIn(("l", "removed", "t"), pairs)
        self.assertIn(("m", "fire", "l-added"), pairs)
        self.assertFalse(upgrade.events(doc))


class EventOutsTests(TestCase):
    def test_events_have_no_player_and_manual_has_author(self):
        for name in ("signal", "on:time", "on:tag", "on:machine.status", "on:air.station", "on:layer.added"):
            self.assertNotIn("player", [s.name for s in N.DATA_OUTS[name]], name)
        self.assertIn("player", [s.name for s in N.DATA_OUTS["on:air.sent"]])
        self.assertEqual([s.name for s in N.DATA_OUTS["manual"]], ["author"])
        boss = get_user_model().objects.create_user("boss", is_staff=True)
        graph = make([node("m", "manual"), node("t", "act:tag", variant="on", owner="world", name="x")], [wire("m", "fire", "t")], slug="man")
        run = runtime.start_manual(graph, "m", author=boss)
        self.assertEqual(value_of(run, Doc(graph.doc), "m", "author"), "boss")


class FlowNodesTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_turns_stop(self):
        graph = make([node("m", "manual"), node("t", "turns", count=2, cycle="stop"), node("a", "do:world_count", name="b1"),
                      node("b", "do:world_count", name="b2"), node("o", "do:world_count", name="over")],
                     [wire("m", "fire", "t"), wire("t", "b1", "a"), wire("t", "b2", "b"), wire("t", "over", "o")], slug="tt")
        for _ in range(4):
            runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual([values.get(values.COUNT, "world", 0, n) for n in ("b1", "b2", "over")], [1, 1, 2])
        self.assertIn("over", N.sockets(N.KINDS["turns"], {"cycle": "stop"}, "out"))
        self.assertNotIn("over", N.sockets(N.KINDS["turns"], {}, "out"))

    def test_some_of_inputs(self):
        graph = make([node("m", "manual"), node("s", "join", mode="count", count=4, need=2), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "s", "i1"), wire("m", "fire", "s", "i3"), wire("s", "next", "a")], slug="so")
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(values.get(values.COUNT, "world", 0, "c"), 1)

    def test_choose_becomes_if_chain(self):
        doc = {"nodes": [node("m", "manual"), node("c", "choose", rows=[{"label": "a", "condition": "tag:a"}, {"label": "b", "condition": "tag:b"}]),
                         node("x", "act:tag"), node("y", "act:tag"), node("z", "act:tag")],
               "wires": [wire("m", "fire", "c"), wire("c", "r1", "x"), wire("c", "r2", "y"), wire("c", "else", "z")]}
        self.assertTrue(upgrade.flow_nodes(doc))
        kinds = {n["id"]: (n["type"], n["data"]) for n in doc["nodes"]}
        self.assertEqual((kinds["c"], kinds["c-2"]), (("check", {"condition": "tag:a"}), ("check", {"condition": "tag:b"})))
        pairs = {(w["from"], w["out"], w["to"]) for w in doc["wires"]}
        self.assertTrue({("m", "fire", "c"), ("c", "yes", "x"), ("c", "no", "c-2"), ("c-2", "yes", "y"), ("c-2", "no", "z")} <= pairs)
        self.assertFalse(upgrade.flow_nodes(doc))


class FamilyTests(TestCase):
    def test_route_and_wait_families(self):
        kinds = {k["name"]: k for k in N.catalog()["kinds"]}
        self.assertEqual([n for n, k in kinds.items() if k["family"] == "Направить"], ["check", "random", "turns"])
        self.assertEqual(kinds["join"]["family"], "")
        self.assertNotIn("each", kinds)
        self.assertNotIn("watch", kinds)


class WaitUpgradeTests(TestCase):
    def test_condition_and_timeout_go(self):
        doc = {"nodes": [node("w", "wait", mode="condition", condition="tag:x", timeout=5, minutes=3), node("t", "act:tag"), node("n", "wait", mode="until", at="21:00")],
               "wires": [wire("w", "next", "t"), wire("w", "timeout", "t")]}
        self.assertTrue(upgrade.wait_nodes(doc))
        self.assertEqual(doc["nodes"][0]["data"], {"minutes": 3})
        self.assertEqual([(w["out"]) for w in doc["wires"]], ["next"])
        self.assertEqual(doc["nodes"][2]["data"], {"mode": "until", "at": "21:00"})
        self.assertFalse(upgrade.wait_nodes(doc))


class JoinTests(TestCase):
    def test_old_joins_become_one_node(self):
        doc = {"nodes": [node("a", "all", count=3), node("r", "race", count=2), node("s", "some", count=3, need=2), node("x", "act:tag")],
               "wires": [wire("m", "fire", "a", "i1"), wire("m", "fire", "a", "i2"), wire("m", "fire", "r", "i1"), wire("r", "o2", "x"),
                         wire("m", "fire", "s", "i1"), wire("m", "fire", "s", "i3")]}
        self.assertTrue(upgrade.join_nodes(doc))
        kinds = {n["id"]: (n["type"], n["data"]) for n in doc["nodes"]}
        self.assertEqual(kinds["a"], ("join", {"mode": "all", "count": 3}))
        self.assertEqual(kinds["r"], ("join", {"mode": "any", "count": 2}))
        self.assertEqual(kinds["s"], ("join", {"mode": "count", "need": 2, "count": 4}))
        self.assertIn(("r", "next", "x"), [(w["from"], w["out"], w["to"]) for w in doc["wires"]])
        self.assertFalse(upgrade.join_nodes(doc))
