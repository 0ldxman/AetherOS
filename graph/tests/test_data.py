"""Провода данных: выходы событий, ноды данных, входы-поля, типы."""
from engine import values as store
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine.events import emit
from graph import check, runtime
from graph.models import Wait
from graph.tests.test_runtime import counter, make, node, wire


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


class DataTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_event_detail_feeds_an_action_field(self):
        make([node("fl", "on:placement.opened", path="/home/*"), node("u", "ent:account"), node("a", "act:tag", variant="on")],
             [wire("fl", "opened", "a"), f("fl", "login", "u", "account"), f("u", "login", "a", "name")])
        from machines.models import Machine, MachineProfile

        MachineProfile.objects.create(machine=Machine.objects.create(name="Core", hostname="core"), login="vault", name="Vault")
        emit("file.read", self.ivan, machine="core", login="ivan", path="/srv/x", item="other")
        emit("file.read", self.ivan, machine="core", login="vault", path="/home/x", item="vault")
        self.assertTrue(store.on("world", 0, "vault"))

    def test_template_number_and_player(self):
        subs = [{"id": "s1", "name": "игрок"}, {"id": "s2", "name": "n"}, {"id": "s3", "name": "тег", "value": "z"}]
        make([node("m", "manual"), node("t", "text", value="{игрок}-{n}-{тег}", subs=subs), node("n", "number", value=3),
              node("a", "do:flag"), node("p", "ent:player")],
             [wire("m", "fire", "a"), f("p", "value", "t", "s1"), f("n", "value", "t", "s2"), f("t", "value", "a", "name")])
        from graph.models import Graph

        runtime.start_manual(Graph.objects.get(), "m", self.ivan)
        self.assertTrue(store.on("player", self.ivan.pk, "ivan-3-z"))

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
        graph = make([node("m", "manual"), node("c", "check"), node("fa", "fact", expr="tag:x"), node("nt", "logic", op="not"),
                      node("o", "logic", op="or", values=[{"id": "v1"}, {"id": "v2"}]),
                      node("b", "boolean", value=False), node("y", "do:world_count", name="yes")],
                     [wire("m", "fire", "c"), f("fa", "value", "nt", "v1"), f("nt", "value", "o", "v1"), f("b", "value", "o", "v2"),
                      f("o", "value", "c", "condition"), wire("c", "yes", "y")])
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        store.set_tag("player", self.ivan.pk, "x")
        runtime.start_manual(graph, "m", self.ivan)
        self.assertEqual(counter("yes"), 1)

    def test_math(self):
        graph = make([node("m", "manual"), node("x", "math", op="mul", a=4), node("n", "number", value=5), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "a"), f("n", "value", "x", "b"), f("x", "value", "a", "delta")])
        runtime.start_manual(graph, "m")
        self.assertEqual(counter(), 20)

    def test_unknown_substitution_stays(self):
        from graph.runtime import Doc, value_of

        doc = Doc({"nodes": [{"id": "t", "type": "text", "data": {"value": "a-{нет}", "subs": [{"id": "s1", "name": "да", "value": "1"}]}}]})
        self.assertEqual(value_of(None, doc, "t", "value"), "a-{нет}")

    def test_switch_picks_by_condition(self):
        from graph.runtime import Doc, value_of

        for condition, expected in ((True, "night"), (False, "no pass"), (1, "night"), ("", "no pass")):
            doc = Doc({"nodes": [{"id": "s", "type": "switch", "data": {"condition": condition, "yes": "night", "no": "no pass"}}]})
            self.assertEqual(value_of(None, doc, "s", "value"), expected)

    def test_logic_ops_over_many_inputs(self):
        from graph.runtime import Doc, value_of

        cases = {("and", (True, True, True)): True, ("and", (True, False, True)): False, ("or", (False, False, True)): True,
                 ("xor", (True, False, False)): True, ("xor", (True, True, False)): False, ("not", (True,)): False, ("and", ()): False}
        for (op, values), expected in cases.items():
            rows = [{"id": f"v{i + 1}", "value": v} for i, v in enumerate(values)]
            doc = Doc({"nodes": [{"id": "l", "type": "logic", "data": {"op": op, "values": rows}}]})
            self.assertEqual(value_of(None, doc, "l", "value"), expected, (op, values))

    def test_math_ops(self):
        from graph.runtime import Doc, value_of

        for op, a, b, expected in (("mod", 7, 3, 1), ("pow", 2, 10, 1024), ("round", 2.6, None, 3), ("floor", 2.6, None, 2),
                                   ("ceil", 2.1, None, 3), ("abs", -4, None, 4), ("neg", 5, None, -5), ("div", 1, 0, 0), ("pow", 10, 1000, 0)):
            doc = Doc({"nodes": [{"id": "x", "type": "math", "data": {"op": op, "a": a, "b": b}}]})
            self.assertEqual(value_of(None, doc, "x", "value"), expected, op)

    def test_row_inputs_are_typed_and_checked(self):
        graph = make([node("t", "text", value="x"), node("l", "logic", op="and"), node("tp", "text", value="{a}")],
                     [f("t", "value", "l", "v1"), f("t", "value", "tp", "s1"), f("t", "value", "tp", "zz")])
        texts = [p["text"] for p in check.problems(graph.doc)]
        self.assertIn("«v1» ждёт да/нет, а приходит текст", texts)
        self.assertTrue(any("нет входа «zz»" in t for t in texts))

    def test_waiting_filter_from_a_wire_is_frozen_on_the_wait(self):
        graph = make([node("m", "manual"), node("t", "text", value="/srv/*"), node("fl", "on:placement.opened"), node("a", "do:world_count", name="c")],
                     [wire("m", "fire", "fl"), f("t", "value", "fl", "path"), wire("fl", "opened", "a")])
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
        self.assertTrue(store.on("world", 0, "deep"))


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
