"""Списки: тип «список из X», ноды «Список: …» и «Для каждого»."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from graph import check, nodes, runtime
from graph.runtime import Doc, value_of
from graph.tests.test_runtime import counter, make, node, wire


def f(src, out, dst, field):
    return wire(src, out, dst, f"f:{field}")


def items(kind="text", *values_):
    return node("l", "list.make", of=kind, items=[{"id": f"e{i}", "value": v} for i, v in enumerate(values_, 1)])


class ListTypeTests(TestCase):
    def test_compatibility(self):
        self.assertTrue(nodes.compatible("text", "list:text"))                  # одно значение — список из одного
        self.assertTrue(nodes.compatible("list:number", "list:text"))
        self.assertTrue(nodes.compatible("list:item", "text"))                   # список в текст — через запятую
        self.assertTrue(nodes.compatible("list:machine", "list:any"))
        self.assertFalse(nodes.compatible("list:text", "number"))
        self.assertFalse(nodes.compatible("event", "list:text"))

    def test_element_type_follows_the_node(self):
        kind = nodes.KINDS["list.content"]
        self.assertEqual(nodes.sock_type(kind, {"of": "machine"}, "in", "f:list"), "list:machine")
        self.assertEqual(nodes.sock_type(kind, {"of": "machine", "mode": "item"}, "out", "item"), "machine")
        self.assertEqual(nodes.sock_type(kind, {"mode": "item"}, "out", "item"), "text")
        self.assertEqual(nodes.sockets(kind, {"mode": "item"}, "out"), ["item", "found"])
        self.assertEqual(nodes.KINDS["list.make"].types_from, ("@rows",))
        graph = {"nodes": [node("c", "ent:character"), node("i", "list.content", of="machine")], "wires": [f("c", "value", "i", "list")]}
        self.assertIn("«Список» ждёт список (машина), а приходит персонажа", [p["text"] for p in check.problems(graph)])


class ListNodeTests(TestCase):
    def get(self, nodes_, wires, node_id, out="value"):
        return value_of(None, Doc({"nodes": nodes_, "wires": wires}), node_id, out)

    def test_make_count_item_has(self):
        base = [items("text", "a", "", "B")]
        self.assertEqual((self.get(base, [], "l"), self.get(base, [], "l", "count")), (["a", "B"], 2))
        self.assertEqual(self.get(base + [node("c", "list.content")], [f("l", "value", "c", "list")], "c", "count"), 2)
        last = node("i", "list.content", mode="item", pick="last")
        self.assertEqual(self.get(base + [last], [f("l", "value", "i", "list")], "i", "item"), "B")
        far = node("i", "list.content", mode="item", pick="number", number=5)
        self.assertEqual((self.get(base + [far], [f("l", "value", "i", "list")], "i", "item"), self.get(base + [far], [f("l", "value", "i", "list")], "i", "found")),
                         (None, False))
        has = node("h", "list.content", mode="has", value="b")
        self.assertTrue(self.get(base + [has], [f("l", "value", "h", "list")], "h", "has"))

    def test_add_remove_take(self):
        base = [items("text", "a", "b", "c")]
        wire_ = [f("l", "value", "x", "list")]

        def act(**data):
            return self.get(base + [node("x", "list.action", **data)], wire_, "x", "list")

        self.assertEqual(act(value="d"), ["a", "b", "c", "d"])
        self.assertEqual(act(value="d", where="start"), ["d", "a", "b", "c"])
        self.assertEqual(act(value="d", where="index", at=2), ["a", "d", "b", "c"])
        self.assertEqual(act(mode="remove"), ["a", "b"])
        self.assertEqual(act(mode="remove", where="start"), ["b", "c"])
        self.assertEqual(act(mode="remove", where="index", at=9), ["a", "b", "c"])
        took = node("x", "list.action", mode="take", by="value", item="B")
        self.assertEqual([self.get(base + [took], wire_, "x", out) for out in ("list", "item", "found")], [["a", "c"], "b", True])
        took = node("x", "list.action", mode="take", number=7)
        self.assertEqual([self.get(base + [took], wire_, "x", out) for out in ("list", "item", "found")], [["a", "b", "c"], None, False])

    def test_single_value_becomes_a_list_and_a_list_becomes_text(self):
        nodes_ = [node("t", "text", value="solo"), node("c", "list.content"), items("text", "x", "y"), node("tp", "text", value="{all}",
                  subs=[{"id": "s1", "name": "all"}])]
        wires = [f("t", "value", "c", "list"), f("l", "value", "tp", "s1")]
        self.assertEqual(self.get(nodes_, wires, "c", "count"), 1)
        self.assertEqual(self.get(nodes_, wires, "tp"), "x, y")


class ForEachTests(TestCase):
    def setUp(self):
        self.ivan = get_user_model().objects.create_user("ivan")

    def test_each_branch_sees_its_element_then_done(self):
        graph = make([node("m", "manual"), items("text", "red", "green", "blue"), node("e", "foreach"),
                      node("t", "act:tag", variant="on", owner="world"), node("d", "do:world_count", name="done")],
                     [wire("m", "fire", "e"), f("l", "value", "e", "list"), wire("e", "each", "t"), f("e", "item", "t", "name"),
                      wire("e", "done", "d")])
        self.assertEqual([p for p in check.problems(graph.doc) if p["level"] == "error"], [])
        runtime.start_manual(graph, "m", self.ivan)
        self.assertTrue(all(values.on("world", 0, name) for name in ("red", "green", "blue")))
        self.assertEqual(counter("done"), 1)

    def test_waiting_inside_each_is_an_error(self):
        doc = {"nodes": [node("m", "manual"), items(), node("e", "foreach"), node("w", "wait", minutes=5)],
               "wires": [wire("m", "fire", "e"), f("l", "value", "e", "list"), wire("e", "each", "w")]}
        self.assertIn("в ветке «Каждый» нельзя ждать: элементы проходят её сразу", [p["text"] for p in check.problems(doc)])
