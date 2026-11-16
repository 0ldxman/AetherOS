"""Сокеты нескольких типов и «одно или список» в нодах: владелец тега по проводу, фильтры событий списком, действия с каждым."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from engine.events import emit
from graph import check, nodes, runtime
from graph.runtime import Doc, value_of
from graph.tests.test_runtime import counter, make, node, wire
from machines.models import Machine


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


def machines(*hosts):
    return node("l", "list.make", of="machine", items=[{"id": f"e{i}", "value": h} for i, h in enumerate(hosts, 1)])


class ManySocketTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")
        self.core = Machine.objects.create(name="Core", hostname="core")
        self.main = Machine.objects.create(name="Main", hostname="main")

    def no_errors(self, doc):
        self.assertEqual([p for p in check.problems(doc) if p["level"] == "error"], [])

    def test_owner_by_wire_type(self):
        values.put("machine", self.core.pk, "heat", 7)
        doc = {"nodes": [node("m", "ent:machine", machine="core"), node("c", "ent:count", name="heat")], "wires": [f("m", "value", "c", "thing")]}
        self.no_errors(doc)
        self.assertEqual(value_of(None, Doc(doc), "c", "value"), 7)
        kind = nodes.KINDS["ent:count"]
        self.assertEqual(nodes.sock_type(kind, {}, "in", "f:thing"), "player|character|machine|server|item")
        self.assertEqual(nodes.sock_type(nodes.KINDS["act:tag"], {}, "in", "f:thing"), "many:player|character|machine|server|item")

    def test_tag_each_machine_of_a_list(self):
        graph = make([node("m", "manual"), machines("core", "main"), node("t", "act:tag", variant="on", name="hacked")],
                     [wire("m", "fire", "t"), f("l", "value", "t", "thing")])
        self.no_errors(graph.doc)
        runtime.start_manual(graph, "m", self.ivan)
        self.assertTrue(values.on("machine", self.core.pk, "hacked") and values.on("machine", self.main.pk, "hacked"))

    def test_event_filter_takes_any_of_a_list(self):
        graph = make([node("m", "manual"), node("l", "list.make", of="item", items=[{"id": "e1", "value": "clue-a"}, {"id": "e2", "value": "clue-b"}]),
                      node("w", "on:placement.opened"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), f("l", "value", "w", "item"), wire("w", "opened", "a")])
        self.no_errors(graph.doc)
        runtime.start_manual(graph, "m", self.ivan)
        emit("file.read", self.ivan, machine="core", path="/x", item="other")
        self.assertEqual(counter(), 0)
        emit("file.read", self.ivan, machine="core", path="/y", item="clue-b")
        self.assertEqual(counter(), 1)

    def test_tag_event_on_any_machine_of_a_list(self):
        graph = make([node("m", "manual"), machines("core", "main"), node("w", "on:tag", name="hacked"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "w"), f("l", "value", "w", "thing"), wire("w", "set", "a")])
        self.no_errors(graph.doc)
        runtime.start_manual(graph, "m", self.ivan)
        values.set_tag("machine", self.main.pk, "hacked")
        self.assertEqual(counter(), 1)

    def test_contains_any_and_server_type(self):
        doc = {"nodes": [machines("core", "main"), node("v", "list.make", of="machine", items=[{"id": "e1", "value": "x"}, {"id": "e2", "value": "main"}]),
                         node("h", "list.content", of="machine", mode="has")], "wires": [f("l", "value", "h", "list"), f("v", "value", "h", "value")]}
        self.no_errors(doc)
        self.assertTrue(value_of(None, Doc(doc), "h", "has"))
        self.assertEqual(nodes.sock_type(nodes.KINDS["do:net_node"], {}, "in", "f:address"), "server")
        self.assertEqual(nodes.sock_type(nodes.KINDS["find"], {}, "in", "f:item"), "many:item")
        self.assertEqual(nodes.sock_type(nodes.KINDS["act:machine.status"], {}, "in", "f:host"), "many:machine")

    def test_owner_table(self):
        graph = make([node("m", "manual"), node("e", "ent:machine", machine="core"), node("p", "ent:player", player="ivan"),
                      node("w", "act:tag", variant="on", name="world-tag"),
                      node("me", "act:tag", variant="on", scope="player", name="my-tag"),
                      node("pair", "act:tag", variant="on", scope="player", name="pair-tag"),
                      node("shared", "act:tag", variant="on", name="core-tag"),
                      node("pl", "act:tag", variant="on", name="ivan-tag")],
                     [wire("m", "fire", "w"), wire("w", "next", "me"), wire("me", "next", "pair"), wire("pair", "next", "shared"),
                      wire("shared", "next", "pl"), f("e", "value", "pair", "thing"), f("e", "value", "shared", "thing"), f("p", "value", "pl", "thing")])
        self.no_errors(graph.doc)
        runtime.start_manual(graph, "m", self.ivan)
        self.assertTrue(values.on("world", 0, "world-tag"))
        self.assertTrue(values.on("player", self.ivan.pk, "my-tag"))
        self.assertTrue(values.on("machine", self.core.pk, "pair-tag", self.ivan) and not values.on("machine", self.core.pk, "pair-tag"))
        self.assertTrue(values.on("machine", self.core.pk, "core-tag"))
        self.assertTrue(values.on("player", self.ivan.pk, "ivan-tag"))
        names = [f.name for f in nodes.KINDS["act:tag"].fields]
        self.assertNotIn("owner", names)
        self.assertNotIn("machine", names)
