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
