"""Провода данных: выходы событий, ноды данных, входы-поля, типы."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine.events import emit
from graph import check, runtime
from graph.models import Wait
from graph.tests.test_runtime import counter, make, node, wire
from mail.models import Flag
from world.models import WorldFlag


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


class DataTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_event_detail_feeds_an_action_field(self):
        make([node("fl", "file", path="/home/*"), node("a", "do:world_flag")],
             [wire("fl", "read", "a"), f("fl", "layer", "a", "name")])
        emit("file.read", self.ivan, path="/home/x", layer="vault")
        self.assertTrue(WorldFlag.objects.get(name="vault").on)

    def test_template_number_and_player(self):
        make([node("m", "manual"), node("t", "template", template="{a}-{b}"), node("n", "number", value=3), node("a", "do:flag")],
             [wire("m", "fire", "a"), f("m", "player", "t", "a"), f("n", "value", "t", "b"), f("t", "value", "a", "name")])
        from graph.models import Graph

        runtime.start_manual(Graph.objects.get(), "m", self.ivan)
        self.assertTrue(Flag.objects.filter(user=self.ivan, name="ivan-3").exists())

    def test_condition_from_wires(self):
        doc = [node("m", "manual"), node("c", "check"), node("cmp", "compare", op="ge"), node("cnt", "read", what="world_counter", name="frag"),
               node("n", "number", value=2), node("y", "do:world_count", name="yes"), node("no", "do:world_count", name="no")]
        wires = [wire("m", "fire", "c"), f("cmp", "value", "c", "condition"), f("cnt", "value", "cmp", "a"), f("n", "value", "cmp", "b"),
                 wire("c", "yes", "y"), wire("c", "no", "no")]
        graph = make(doc, wires)
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m")
        from world import state

        state.count("frag", 2)
        runtime.start_manual(graph, "m")
        self.assertEqual((counter("yes"), counter("no")), (1, 1))

    def test_logic_and_fact(self):
        graph = make([node("m", "manual"), node("c", "check"), node("fa", "fact", expr="flag:x"), node("nt", "not"), node("o", "or"),
                      node("b", "boolean", value=False), node("y", "do:world_count", name="yes")],
                     [wire("m", "fire", "c"), f("fa", "value", "nt", "a"), f("nt", "value", "o", "a"), f("b", "value", "o", "b"),
                      f("o", "value", "c", "condition"), wire("c", "yes", "y")])
        runtime.start_manual(graph, "m", self.ivan)
        Flag.objects.create(user=self.ivan, name="x")
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(counter("yes"), 1)

    def test_math(self):
        graph = make([node("m", "manual"), node("x", "math", op="mul", a=4), node("n", "number", value=5), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "a"), f("n", "value", "x", "b"), f("x", "value", "a", "delta")])
        runtime.start_manual(graph, "m")
        self.assertEqual(counter(), 20)

    def test_waiting_filter_from_a_wire_is_frozen_on_the_wait(self):
        graph = make([node("m", "manual"), node("t", "text", value="/srv/*"), node("fl", "file"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "fl"), f("t", "value", "fl", "path"), wire("fl", "read", "a")])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(Wait.objects.get().data, {"path": "/srv/*"})
        emit("file.read", self.ivan, path="/home/x")
        self.assertEqual(counter(), 0)
        emit("file.read", self.ivan, path="/srv/x")
        self.assertEqual(counter(), 1)

    def test_data_through_a_group(self):
        group = {"title": "G", "nodes": [node("i", "group_in", sockets=[{"name": "go", "label": "go"}, {"name": "v", "label": "v", "type": "text"}]),
                                         node("a", "do:world_flag")],
                 "wires": [wire("i", "go", "a"), f("i", "v", "a", "name")]}
        from graph.models import Graph

        doc = {"nodes": [node("m", "manual"), node("t", "text", value="deep"), node("g", "group", group="grp")],
               "wires": [wire("m", "fire", "g", "go"), wire("t", "value", "g", "v")], "groups": {"grp": group}}
        graph = Graph.objects.create(slug="g", title="g", active=True, doc=doc)
        runtime.rebuild_starts(graph)
        self.assertEqual([p for p in check.problems(doc, "g") if p["level"] == "error"], [])
        runtime.start_manual(graph, "m")
        self.assertTrue(WorldFlag.objects.get(name="deep").on)


class TypeTests(TestCase):
    def test_types_are_checked(self):
        doc = {"nodes": [node("m", "manual"), node("n", "number", value=1), node("b", "boolean"), node("a", "do:world_flag", name="x"),
                         node("c", "check")],
               "wires": [wire("m", "fire", "a"), f("n", "value", "a", "name"), wire("n", "value", "c"), f("m", "fire", "c", "condition")]}
        found = [p["text"] for p in check.problems(doc)]
        self.assertIn("«Метка мира» ждёт метку мира, а приходит число", found)
        self.assertTrue(any("вход ждёт событие, а приходит число" in t for t in found))
        self.assertTrue(any("«Условие» ждёт да/нет, а приходит событие" in t for t in found))

    def test_compatibility(self):
        from graph.nodes import compatible

        self.assertTrue(compatible("number", "text"))
        self.assertTrue(compatible("text", "machine"))
        self.assertFalse(compatible("event", "bool"))
        self.assertFalse(compatible("item", "character"))
