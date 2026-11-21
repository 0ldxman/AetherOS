"""«Управление»: кнопка, переключатель, текстовый ввод, выбор, число — пульт автора на странице «Мир»."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from engine import values
from graph import check, nodes as N
from graph.models import Shared
from graph.runtime import start_control, start_manual
from graph.tests.test_runtime import make, node, wire


def count(name):
    return values.get(values.COUNT, "world", 0, name)


class ControlTests(TestCase):
    def setUp(self):
        self.author = get_user_model().objects.create_user("author", is_staff=True)

    def graph(self, nodes, wires, slug="panel"):
        return make(nodes, wires, slug=slug)

    def test_family_and_kinds(self):
        self.assertEqual({N.KINDS[name].family for name in N.CONTROLS}, {"Управление"})
        self.assertEqual(N.KINDS["manual"].label, "Управление: Кнопка")

    def test_switch_writes_variable_and_starts_by_state(self):
        graph = self.graph([node("s", "ctl_switch", name="Alarm"), node("a", "do:world_count", name="on"), node("b", "do:world_count", name="off")],
                           [wire("s", "on", "a"), wire("s", "off", "b")])
        self.assertEqual(check.problems(graph.doc), [])
        start_control(graph, "s", True, author=self.author)
        self.assertEqual((Shared.objects.get(graph=graph).data, count("on"), count("off")), ({"Alarm": True}, 1, 0))
        start_control(graph, "s", False)
        self.assertEqual((Shared.objects.get(graph=graph).data, count("on"), count("off")), ({"Alarm": False}, 1, 1))

    def test_text_and_value_output(self):
        graph = self.graph([node("t", "ctl_text", name="Password"), node("a", "do:world_count", name="x")], [wire("t", "set", "a"), wire("t", "value", "a", "f:name")])
        start_control(graph, "t", "opened")
        self.assertEqual((Shared.objects.get(graph=graph).data, count("opened")), ({"Password": "opened"}, 1))

    def test_choice_accepts_only_listed_options(self):
        graph = self.graph([node("c", "ctl_choice", name="Mode", options="calm\nalert")], [])
        start_control(graph, "c", "alert")
        self.assertEqual(Shared.objects.get(graph=graph).data, {"Mode": "alert"})
        with self.assertRaises(ValueError):
            start_control(graph, "c", "panic")

    def test_number_within_bounds_and_condition(self):
        graph = self.graph([node("n", "ctl_number", name="Level", min=0, max=10), node("g", "check", condition="var:Level>=5"),
                            node("y", "do:world_count", name="high"), node("l", "do:world_count", name="low")],
                           [wire("n", "set", "g"), wire("g", "yes", "y"), wire("g", "no", "l")])
        start_control(graph, "n", 7)
        start_control(graph, "n", 2)
        self.assertEqual((count("high"), count("low"), Shared.objects.get(graph=graph).data), (1, 1, {"Level": 2}))
        with self.assertRaises(ValueError):
            start_control(graph, "n", 11)
        with self.assertRaises(ValueError):
            start_control(graph, "n", "many")

    def test_button_starts_and_other_nodes_are_refused(self):
        graph = self.graph([node("m", "manual", name="Go"), node("a", "do:world_count", name="pressed"), node("x", "do:world_count", name="other")], [wire("m", "fire", "a")])
        start_control(graph, "m", author=self.author)
        start_manual(graph, "m")
        self.assertEqual(count("pressed"), 2)
        with self.assertRaises(ValueError):
            start_control(graph, "x")

    def test_control_wakes_wait_for_condition(self):
        users = get_user_model().objects.create_user("ivan")
        graph = self.graph([node("m", "manual"), node("w", "wait_cond", condition="var:Alarm"), node("a", "do:world_count", name="woke"),
                            node("s", "ctl_switch", name="Alarm")], [wire("m", "fire", "w"), wire("w", "next", "a")])
        start_manual(graph, "m", users)
        self.assertEqual(count("woke"), 0)
        start_control(graph, "s", True)
        self.assertEqual(count("woke"), 1)

    def test_control_name_counts_as_written_variable(self):
        doc = {"nodes": [node("s", "ctl_switch", name="Alarm"), node("m", "manual"), node("c", "check", condition="var:Alarm"), node("x", "check", condition="var:Typo")],
               "wires": [wire("m", "fire", "c"), wire("m", "fire", "x")]}
        texts = [p["text"] for p in check.problems(doc) if p["level"] == "warning"]
        self.assertTrue(any("«Typo»" in t for t in texts))
        self.assertFalse(any("«Alarm»" in t for t in texts))
